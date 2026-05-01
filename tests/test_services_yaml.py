from pathlib import Path

import yaml


def test_send_command_documents_result_field():
    services = yaml.safe_load(
        Path("custom_components/yeelight_pro/services.yaml").read_text()
    )

    assert "result" in services["send_command"]["fields"]
