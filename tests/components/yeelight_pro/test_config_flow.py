import pytest

from homeassistant import config_entries, data_entry_flow
from homeassistant.const import CONF_HOST
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.yeelight_pro.core.const import (
    CONF_KEEPALIVE,
    CONF_PID,
    CONF_PORT,
    CONF_TRANSITION_TIME,
    DOMAIN,
    PID_GATEWAY,
    PID_WIFI_PANEL,
)


class FakeGateway:
    def __init__(self, error=None):
        self._error = error

    async def check_available(self):
        return self._error


async def test_config_flow_shows_user_form(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {}


async def test_config_flow_user_success(hass, monkeypatch):
    seen = {}

    async def fake_get_gateway_from_config(hass_, cfg, renew=False):
        seen["cfg"] = cfg
        seen["renew"] = renew
        return FakeGateway()

    monkeypatch.setattr(
        "custom_components.yeelight_pro.config_flow.get_gateway_from_config",
        fake_get_gateway_from_config,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY},
    )

    assert result["type"] == "create_entry"
    assert result["title"] == "1.2.3.4"
    assert result["data"] == {CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY}
    assert seen["cfg"] == {CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY}
    assert seen["renew"] is True


async def test_config_flow_user_cannot_access(hass, monkeypatch):
    async def fake_get_gateway_from_config(hass_, cfg, renew=False):
        return FakeGateway(error=Exception("boom"))

    monkeypatch.setattr(
        "custom_components.yeelight_pro.config_flow.get_gateway_from_config",
        fake_get_gateway_from_config,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY},
    )

    assert result["type"] == "form"
    assert result["step_id"] == "user"
    assert result["errors"] == {"base": "cannot_access"}
    assert result["description_placeholders"] == {"tip": "boom"}


async def test_config_flow_duplicate_host_aborts(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Existing",
        unique_id="1.2.3.4",
        data={CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY},
    )
    entry.add_to_hass(hass)

    async def fake_get_gateway_from_config(*_args, **_kwargs):
        pytest.fail("Gateway availability should not be checked for duplicates")

    monkeypatch.setattr(
        "custom_components.yeelight_pro.config_flow.get_gateway_from_config",
        fake_get_gateway_from_config,
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": config_entries.SOURCE_USER},
        data={CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY},
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_options_flow_success_updates_entry_and_options(hass, monkeypatch):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old Host",
        data={CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY},
        options={CONF_PORT: 65443},
    )
    entry.add_to_hass(hass)

    seen = {}

    async def fake_get_gateway_from_config(hass_, cfg, renew=False):
        seen["cfg"] = cfg
        seen["renew"] = renew
        return FakeGateway()

    monkeypatch.setattr(
        "custom_components.yeelight_pro.config_flow.get_gateway_from_config",
        fake_get_gateway_from_config,
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        user_input={
            CONF_HOST: "2.3.4.5",
            CONF_PID: PID_WIFI_PANEL,
            CONF_PORT: 12345,
            CONF_KEEPALIVE: 60,
            CONF_TRANSITION_TIME: 1.5,
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"] == {
        CONF_PORT: 12345,
        CONF_KEEPALIVE: 60,
        CONF_TRANSITION_TIME: 1.5,
    }
    assert entry.title == "2.3.4.5"
    assert entry.data == {CONF_HOST: "2.3.4.5", CONF_PID: PID_WIFI_PANEL}
    assert seen["renew"] is True


@pytest.mark.parametrize(
    "user_input",
    [
        {CONF_HOST: "2.3.4.5", CONF_PORT: 70000},
        {CONF_HOST: "2.3.4.5", CONF_KEEPALIVE: 1},
        {CONF_HOST: "2.3.4.5", CONF_TRANSITION_TIME: 0.1},
    ],
)
async def test_options_flow_invalid_ranges_are_rejected_by_schema(hass, user_input):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Old Host",
        data={CONF_HOST: "1.2.3.4", CONF_PID: PID_GATEWAY},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    with pytest.raises(data_entry_flow.InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"],
            user_input=user_input,
        )
