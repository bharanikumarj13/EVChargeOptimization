import pytest
from app.integrations.station_mapper import (
    StationMapper,
    MappingVerificationStatus,
    IntegrationProfile,
)
from app.core.exceptions import StationMappingError


@pytest.fixture(autouse=True)
def reset_mapper():
    StationMapper.reset_to_defaults()
    yield
    StationMapper.reset_to_defaults()


def test_station_mapper_five_station_mock_preservation():
    # In default profile ('five_station_mock'), all 5 internal stations are active
    StationMapper.set_profile("five_station_mock")
    stations = StationMapper.get_profile_stations()
    assert stations == ["STN-01", "STN-02", "STN-03", "STN-04", "STN-05"]
    assert StationMapper.get_profile() == "five_station_mock"


def test_station_mapper_three_station_integration_profile():
    # In 'three_station_integration' profile, exactly 3 stations are active
    StationMapper.set_profile("three_station_integration")
    stations = StationMapper.get_profile_stations()
    assert stations == ["STN-01", "STN-02", "STN-03"]
    assert StationMapper.get_profile() == "three_station_integration"

    # Supported predictor stations
    supported_ext = StationMapper.get_supported_predictor_stations()
    assert supported_ext == ["ST-001", "ST-002", "ST-003"]


def test_station_mapper_unsupported_stations_rejected_in_live():
    # STN-04 and STN-05 are not supported by the EVCharge-Predict model
    with pytest.raises(StationMappingError) as exc_4:
        StationMapper.to_external("STN-04", validate_predictor_support=True)
    assert "not supported by the EVCharge-Predict model" in exc_4.value.message

    with pytest.raises(StationMappingError) as exc_5:
        StationMapper.to_external("STN-05", validate_predictor_support=True)
    assert "not supported by the EVCharge-Predict model" in exc_5.value.message

    # External ST-004 / ST-005 directly rejected
    with pytest.raises(StationMappingError):
        StationMapper.to_external("ST-004", validate_predictor_support=True)


def test_station_mapper_unconfirmed_physical_correspondence_safeguard():
    # Proposed candidate mappings must be UNCONFIRMED_PROPOSAL by default
    assert not StationMapper.is_physically_confirmed("STN-01")
    assert not StationMapper.is_physically_confirmed("STN-02")
    assert not StationMapper.is_physically_confirmed("STN-03")

    # In live path requiring physical verification, unconfirmed mapping raises explicit StationMappingError
    with pytest.raises(StationMappingError) as exc_info:
        StationMapper.to_external("STN-01", require_physical_confirmed=True)
    assert "UNCONFIRMED" in exc_info.value.message
    assert "Caltech source ID: 1-39-139-650" in exc_info.value.message

    with pytest.raises(StationMappingError):
        StationMapper.to_internal("ST-001", require_physical_confirmed=True)


def test_station_mapper_confirm_physical_mapping():
    # Confirming physical mapping transitions status to CONFIRMED_PHYSICAL
    StationMapper.confirm_mapping("STN-01", "ST-001", caltech_source_id="1-39-139-650")
    assert StationMapper.is_physically_confirmed("STN-01")

    # Now to_external and to_internal succeed even with require_physical_confirmed=True
    ext = StationMapper.to_external("STN-01", require_physical_confirmed=True)
    assert ext == "ST-001"
    int_id = StationMapper.to_internal("ST-001", require_physical_confirmed=True)
    assert int_id == "STN-01"


def test_station_mapper_duplicate_and_ambiguous_registration_rejected():
    # Re-registering an internal station to a different external station is rejected as ambiguous
    with pytest.raises(StationMappingError) as exc_internal:
        StationMapper.register_mapping("STN-01", "ST-999")
    assert "already mapped" in exc_internal.value.message

    # Re-registering an external station to a different internal station is rejected as ambiguous
    with pytest.raises(StationMappingError) as exc_external:
        StationMapper.register_mapping("STN-CUSTOM-01", "ST-001")
    assert "already mapped" in exc_external.value.message


def test_station_mapper_missing_mapping_rejected():
    with pytest.raises(StationMappingError):
        StationMapper.to_external("UNKNOWN-STATION")

    with pytest.raises(StationMappingError):
        StationMapper.to_internal("UNKNOWN-STATION")

    with pytest.raises(StationMappingError):
        StationMapper.to_external("")

    with pytest.raises(StationMappingError):
        StationMapper.to_internal("")


def test_station_mapper_details_reporting():
    details = StationMapper.get_all_mapping_details()
    assert len(details) >= 5
    stn1 = next(d for d in details if d["internal_id"] == "STN-01")
    assert stn1["external_id"] == "ST-001"
    assert stn1["caltech_source_id"] == "1-39-139-650"
    assert stn1["verification_status"] == "UNCONFIRMED_PROPOSAL"
    assert stn1["is_physically_confirmed"] is False
    assert stn1["supported_by_predictor_model"] is True

    stn4 = next(d for d in details if d["internal_id"] == "STN-04")
    assert stn4["verification_status"] == "UNSUPPORTED_BY_MODEL"
    assert stn4["supported_by_predictor_model"] is False
