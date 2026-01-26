"""
Manhua Translation CLI.

Command-line interface for local image translation.

Usage:
    python -m scripts.cli translate <image_path>
    python -m scripts.cli batch <directory>
"""

import asyncio
import sys
from functools import lru_cache
from pathlib import Path

import click
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.models import TaskContext
from core.pipeline import Pipeline


console = Console()


@lru_cache(maxsize=1)
def get_pipeline() -> Pipeline:
    """Get cached Pipeline instance to avoid repeated model loading."""
    console.print("[dim]Initializing pipeline...[/dim]")
    return Pipeline()


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Manhua Translation CLI - AI-powered manga translation."""
    pass


@cli.command()
@click.argument("image_path", type=click.Path(exists=True))
@click.option("--source", "-s", default="en", help="Source language (default: en)")
@click.option("--target", "-t", default="zh-CN", help="Target language (default: zh-CN)")
@click.option("--output", "-o", default=None, help="Output directory")
def translate(image_path: str, source: str, target: str, output: str):
    """Translate a single manga image."""
    
    async def run():
        # Use cached pipeline
        pipeline = get_pipeline()
        
        context = TaskContext(
            image_path=image_path,
            source_language=source,
            target_language=target,
        )
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Processing image...", total=None)
            
            result = await pipeline.process(context)
            
            progress.update(task, completed=True)
        
        # Display results
        if result.success:
            console.print("\n[green]✓ Translation completed![/green]")
            console.print(f"  Output: [cyan]{result.task.output_path}[/cyan]")
            console.print(f"  Regions: {len(result.task.regions)}")
            console.print(f"  Time: {result.processing_time_ms:.2f}ms")
            
            # Show regions table
            if result.task.regions:
                table = Table(title="Detected Regions")
                table.add_column("ID", style="dim")
                table.add_column("Source", style="yellow")
                table.add_column("Target", style="green")
                
                for region in result.task.regions:
                    src = (region.source_text or "-")[:30]
                    tgt = (region.target_text or "-")[:30]
                    table.add_row(
                        str(region.region_id)[:8],
                        src + "..." if len(region.source_text or "") > 30 else src,
                        tgt + "..." if len(region.target_text or "") > 30 else tgt,
                    )
                
                console.print(table)
        else:
            console.print(f"\n[red]✗ Translation failed![/red]")
            console.print(f"  Error: {result.task.error_message}")

    asyncio.run(run())


@cli.command()
@click.argument("directory", type=click.Path(exists=True))
@click.option("--source", "-s", default="en", help="Source language (default: en)")
@click.option("--target", "-t", default="zh-CN", help="Target language (default: zh-CN)")
@click.option("--recursive", "-r", is_flag=True, help="Process subdirectories")
@click.option("--concurrent", "-c", default=5, help="Max concurrent tasks")
def batch(directory: str, source: str, target: str, recursive: bool, concurrent: int):
    """Translate all images in a directory."""
    
    async def run():
        dir_path = Path(directory)
        
        # Find images
        patterns = ["*.jpg", "*.jpeg", "*.png", "*.webp"]
        image_files = []
        
        for pattern in patterns:
            if recursive:
                image_files.extend(dir_path.rglob(pattern))
            else:
                image_files.extend(dir_path.glob(pattern))
        
        if not image_files:
            console.print("[yellow]No image files found.[/yellow]")
            return
        
        console.print(f"Found [cyan]{len(image_files)}[/cyan] images to process")
        
        # Create contexts
        contexts = [
            TaskContext(
                image_path=str(img_path),
                source_language=source,
                target_language=target,
            )
            for img_path in image_files
        ]
        
        # Use cached pipeline
        pipeline = get_pipeline()
        
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Processing {len(contexts)} images...",
                total=len(contexts)
            )
            
            results = await pipeline.process_batch(contexts, max_concurrent=concurrent)
            
            progress.update(task, completed=len(contexts))
        
        # Summary
        success_count = sum(1 for r in results if r.success)
        failed_count = len(results) - success_count
        
        console.print(f"\n[green]✓ Completed: {success_count}[/green]")
        if failed_count > 0:
            console.print(f"[red]✗ Failed: {failed_count}[/red]")
        
        # Show failed items
        failed_results = [r for r in results if not r.success]
        if failed_results:
            console.print("\n[red]Failed items:[/red]")
            for r in failed_results:
                console.print(f"  - {r.task.image_path}: {r.task.error_message}")

    asyncio.run(run())


@cli.command()
def info():
    """Show system information."""
    console.print("[bold]Manhua Translation System[/bold]")
    console.print("Version: 0.1.0")
    console.print("\n[dim]Pipeline Stages:[/dim]")
    console.print("  1. OCR (PaddleOCR) - Text detection + recognition")
    console.print("  2. Translator (Google) - Text translation")
    console.print("  3. Inpainter (LaMa) - Text removal")
    console.print("  4. Renderer (TextRenderer) - Text rendering")
    console.print("\n[green]Features:[/green]")
    console.print("  - Dynamic tiling for long images")
    console.print("  - Adjacent region merging")
    console.print("  - SFX detection")
    console.print("  - Chinese typography rules")


if __name__ == "__main__":
    cli()
