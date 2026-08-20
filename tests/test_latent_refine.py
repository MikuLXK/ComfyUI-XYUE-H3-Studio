from core import latent_refine


def test_refine_av_latent_syncs_positive_and_negative(monkeypatch):
    calls = {}
    source = {"samples": object()}
    upscaled = {"samples": object()}

    class ScaleNode:
        def run(self, latent, model_name, scale, device, precision):
            calls["scale"] = (latent, model_name, scale, device, precision)
            return (upscaled,)

    class SyncNode:
        def run(self, latent, positive, negative):
            calls["sync"] = (latent, positive, negative)
            return latent, "positive-synced", "negative-synced"

    monkeypatch.setattr(latent_refine, "_scale_node", lambda: ScaleNode)
    monkeypatch.setattr(latent_refine, "_sync_node", lambda: SyncNode)
    class Separate:
        @classmethod
        def execute(cls, latent):
            return "video", "audio"
    class Concat:
        @classmethod
        def execute(cls, video, audio):
            return upscaled,
    monkeypatch.setattr(latent_refine, "LTXVSeparateAVLatent", Separate)
    monkeypatch.setattr(latent_refine, "LTXVConcatAVLatent", Concat)
    result = latent_refine.refine_av_latent(
        source,
        "positive",
        "negative",
        model_name="h3.safetensors",
        scale=1.5,
    )
    assert result == (upscaled, "positive-synced", "negative-synced")
    assert calls["scale"][0] == "video"
    assert calls["sync"] == (upscaled, "positive", "negative")
