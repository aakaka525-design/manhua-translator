import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { useMangaStore } from "@/stores/manga";
import { useTranslateStore } from "@/stores/translate";

class MockEventSource {
  constructor(url) {
    this.url = url;
    this.onopen = null;
    this.onmessage = null;
    this.onerror = null;
    MockEventSource.instance = this;
  }

  close() {}
}

describe("translate store", () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    MockEventSource.instance = null;
    vi.stubGlobal("EventSource", MockEventSource);
  });

  it("marks chapter as failed when chapter_complete reports zero success", () => {
    const mangaStore = useMangaStore();
    mangaStore.currentManga = { id: "m1" };
    mangaStore.chapters = [
      {
        id: "c1",
        page_count: 5,
        isTranslating: true,
        has_translated: true,
        translated_count: 1,
      },
    ];

    const translateStore = useTranslateStore();
    translateStore.initSSE();

    MockEventSource.instance.onmessage({
      data: JSON.stringify({
        type: "chapter_complete",
        manga_id: "m1",
        chapter_id: "c1",
        success_count: 0,
        total_count: 5,
      }),
    });

    const chapter = mangaStore.chapters[0];
    expect(chapter.isTranslating).toBe(false);
    expect(chapter.has_translated).toBe(false);
    expect(chapter.translated_count).toBe(0);
    expect(chapter.isComplete).toBe(false);
    expect(chapter.statusText).toBe("失败");
  });
});
