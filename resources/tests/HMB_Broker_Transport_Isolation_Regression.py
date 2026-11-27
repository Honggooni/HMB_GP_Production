"""Authenticated non-video operations remain usable when the video node cannot load."""
from __future__ import annotations

from importlib.abc import MetaPathFinder
import io
import json
from pathlib import Path
import sys
from unittest import mock


class BrokenVideoNode(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname == "HMBSeedanceGeneration":
            raise ImportError("Simulated video node import failure")
        return None


def no_socket(event, args):
    if event == "socket.connect":
        raise AssertionError("Offline regression opened a socket")


sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
sys.meta_path.insert(0, BrokenVideoNode())
sys.addaudithook(no_socket)

from PIL import Image

sample = io.BytesIO()
Image.new("RGB", (3, 2)).save(sample, format="PNG")
with mock.patch.dict(sys.modules, {"_hmb_broker_transport": None}):
    from _hmb_image_generation import validate_image_bytes

    local = validate_image_bytes(sample.getvalue())
    assert (local.width, local.height, local.mime_type) == (3, 2, "image/png")

import _hmb_broker_transport as transport
import _hmb_analysis_broker as analysis
import _hmb_image_generation as images
import HMBColorLUTLibrary as lut

origin = analysis.production_origin()
account_path = "/api/me"
analysis_path = "/api/v1/analysis/capabilities"
review_path = "/api/v1/reviews/capabilities"
responses = {
    account_path: {"id": "fixture-owner", "display_name": "Fixture"},
    analysis_path: {
        "schema": "hmb-analysis-capabilities-v1", "enabled": True, "automatic_retries": 0,
        "models": [{"model_id": analysis.MODELS[0], "enabled": True, "kinds": ["image"]}],
    },
    review_path: {
        "schema": "hmb-review-portal", "version": 1, "review_portal": True,
        "page_url": "/reviews", "page_size": 20, "retention_days": 30,
    },
}
requests = []


def respond(request, *, timeout):
    assert request.get_method() == "GET"
    assert request.get_header("Authorization") == "Bearer offline-fixture"
    assert timeout > 0 and request.full_url.startswith(origin + "/api/")
    path = request.full_url[len(origin):]
    requests.append(path)
    response = io.BytesIO(json.dumps(responses[path]).encode())
    response.geturl = lambda: request.full_url
    return response


opener = mock.Mock(open=respond)
with mock.patch.object(transport, "_broker_load_token", return_value="offline-fixture"), \
        mock.patch.object(transport, "_broker_build_opener", return_value=opener):
    image_client = images.ImageGenerationBroker(server_url=origin)
    assert image_client.account_snapshot().connected
    analysis_client = analysis.AnalysisClient(analysis.MODELS[0], "image", is_live=lambda: True)
    assert analysis_client.principal and analysis_client.cache_scope
    assert lut._upload_bridge(origin).review_capabilities()["review_portal"]
    assert requests == [account_path, account_path, analysis_path, review_path]

    with mock.patch.object(transport, "_broker_load_token",
                           side_effect=transport._BrokerAuthenticationError("offline authentication failure")), \
            mock.patch.object(transport, "_broker_migrate_legacy_gateway_token",
                              side_effect=transport._BrokerAuthenticationError("offline authentication failure")):
        try:
            image_client.capabilities()
        except images.ImageGenerationError as exc:
            assert exc.code == "IMAGE_BROKER_LOGIN_REQUIRED", exc.code
        else:
            raise AssertionError("A missing login was accepted")

assert "HMBSeedanceGeneration" not in sys.modules
print("HMB_BROKER_TRANSPORT_ISOLATION=PASS GET=4 external=0 submissions=0")
