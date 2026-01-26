"""
Base module interface for all pipeline stages.

All processing modules must inherit from BaseModule and implement
the async process() method.
"""

from abc import ABC, abstractmethod
from typing import Optional

from ..models import TaskContext


class BaseModule(ABC):
    """
    Abstract base class for all pipeline modules.
    
    Each module receives a TaskContext, processes it, and returns
    the updated TaskContext. Modules should only modify fields
    relevant to their stage.
    """

    def __init__(self, name: Optional[str] = None):
        """
        Initialize the module.
        
        Args:
            name: Optional module name for logging/debugging
        """
        self.name = name or self.__class__.__name__

    @abstractmethod
    async def process(self, context: TaskContext) -> TaskContext:
        """
        Process the task context.
        
        Args:
            context: Current task context with all accumulated data
            
        Returns:
            Updated TaskContext with this module's contributions
            
        Raises:
            Exception: If processing fails
        """
        pass

    async def validate_input(self, context: TaskContext) -> bool:
        """
        Validate that input context has required data.
        
        Override in subclasses to add specific validation.
        
        Args:
            context: Task context to validate
            
        Returns:
            True if valid, False otherwise
        """
        return context.image_path is not None

    def __repr__(self) -> str:
        return f"<{self.name}>"
