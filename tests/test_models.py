"""Tests for telemetry flattening, field classification, and DeviceTelemetry."""

from __future__ import annotations

from custom_components.jackery.models import (
    DeviceTelemetry,
    FieldKind,
    classify_field,
    flatten,
    humanize_field,
)


def test_flatten_nests_dicts_with_dotted_keys() -> None:
    assert flatten({"port": {"ac": {"watts": 42}}}) == {"port.ac.watts": 42}


def test_flatten_indexes_lists() -> None:
    assert flatten({"ports": [{"on": True}, {"on": False}]}) == {
        "ports[0].on": True,
        "ports[1].on": False,
    }


def test_flatten_leaves_scalars_at_top_level() -> None:
    assert flatten({"soc": 87, "model": "Explorer 2000"}) == {"soc": 87, "model": "Explorer 2000"}


def test_classify_percent_like_keys() -> None:
    assert classify_field("soc", 87) is FieldKind.PERCENT
    assert classify_field("batteryLevel", 50) is FieldKind.PERCENT


def test_classify_power_like_keys() -> None:
    assert classify_field("outputWatts", 120) is FieldKind.POWER_W
    assert classify_field("pwrIn", 30) is FieldKind.POWER_W


def test_classify_temperature_voltage_current() -> None:
    assert classify_field("cellTemp", 25) is FieldKind.TEMPERATURE_C
    assert classify_field("busVoltage", 12.6) is FieldKind.VOLTAGE_V
    assert classify_field("outputCurrent", 2.5) is FieldKind.CURRENT_A


def test_classify_boolean_defaults_to_binary_sensor() -> None:
    assert classify_field("chargingFlag", True) is FieldKind.BINARY_SENSOR


def test_classify_boolean_matching_switch_hint_is_switch() -> None:
    assert classify_field("acOutput", True, switch_key_hints=("acoutput",)) is FieldKind.SWITCH


def test_classify_boolean_not_matching_hint_stays_binary_sensor() -> None:
    assert classify_field("faultFlag", True, switch_key_hints=("acoutput",)) is FieldKind.BINARY_SENSOR


def test_classify_generic_numeric_and_text() -> None:
    assert classify_field("someUnknownCounter", 5) is FieldKind.GENERIC_NUMERIC
    assert classify_field("model", "Explorer 2000") is FieldKind.GENERIC_TEXT


def test_classify_ignores_protocol_bookkeeping_fields() -> None:
    assert classify_field("msgId", 12) is FieldKind.IGNORED
    assert classify_field("timestamp", 1710000000) is FieldKind.IGNORED


def test_humanize_field_splits_camel_case_and_strips_prefix() -> None:
    assert humanize_field("port.acOutputWatts") == "Ac Output Watts"
    assert humanize_field("soc") == "Soc"


def test_device_telemetry_merge_updates_fields_and_identity() -> None:
    telemetry = DeviceTelemetry(address="AA:BB:CC:DD:EE:FF")
    telemetry.merge({"soc": 80, "deviceModel": "Explorer 2000 Plus", "fwVersion": "1.2.3"})
    assert telemetry.fields["soc"] == 80
    assert telemetry.model == "Explorer 2000 Plus"
    assert telemetry.firmware_version == "1.2.3"


def test_device_telemetry_merge_is_cumulative_across_calls() -> None:
    telemetry = DeviceTelemetry(address="AA:BB:CC:DD:EE:FF")
    telemetry.merge({"soc": 80})
    telemetry.merge({"outputWatts": 45})
    assert telemetry.fields == {"soc": 80, "outputWatts": 45}
