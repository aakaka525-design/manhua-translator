import { describe, it, expect, vi, beforeEach } from "vitest";
import { setActivePinia, createPinia } from "pinia";
import { useSettingsStore } from "@/stores/settings";

beforeEach(() => {
  setActivePinia(createPinia());
  vi.stubGlobal("fetch", vi.fn());
  localStorage.clear();
});

describe("settings store", () => {
  it("updates upscale settings and calls API", async () => {
    fetch.mockResolvedValue({ ok: true, json: async () => ({}) });
    const store = useSettingsStore();
    await store.selectUpscaleModel({ id: "realesr-animevideov3-x4", name: "AnimeVideo v3" });
    await store.selectUpscaleScale(4);
    expect(fetch).toHaveBeenCalledWith("/api/v1/settings/upscale", expect.any(Object));
    const saved = JSON.parse(localStorage.getItem("manhua_settings"));
    expect(saved.upscaleModel).toBe("realesr-animevideov3-x4");
    expect(saved.upscaleScale).toBe(4);
  });
});
