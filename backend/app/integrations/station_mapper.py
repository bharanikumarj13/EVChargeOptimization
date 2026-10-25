from enum import Enum
from typing import Dict, List, Optional, Set, Any
from app.core.exceptions import StationMappingError
from app.core.config import settings


class MappingVerificationStatus(str, Enum):
    UNCONFIRMED_PROPOSAL = "UNCONFIRMED_PROPOSAL"
    CONFIRMED_PHYSICAL = "CONFIRMED_PHYSICAL"
    UNSUPPORTED_BY_MODEL = "UNSUPPORTED_BY_MODEL"


class IntegrationProfile(str, Enum):
    FIVE_STATION_MOCK = "five_station_mock"
    THREE_STATION_INTEGRATION = "three_station_integration"


class StationMapper:
    """
    Explicit bidirectional mapping layer between EVCharge-Opt internal station IDs (e.g. 'STN-01')
    and EVCharge-Predict canonical external station IDs (e.g. 'ST-001').

    Architectural guarantees:
    1. Rejects the assumption that numeric ID similarity establishes physical station identity.
    2. Keeps proposed candidate mappings explicitly marked as UNCONFIRMED_PROPOSAL until physical correspondence is confirmed.
    3. Prevents sending unsupported station IDs (e.g. 'ST-004', 'ST-005') to the 3-station predictor model.
    4. Supports configurable switching between 'five_station_mock' and 'three_station_integration' profiles.
    5. Rejects missing, duplicate, ambiguous, or unsupported station mappings explicitly without silent zeroing.
    """

    # Canonical station IDs currently supported by the EVCharge-Predict model
    _PREDICTOR_SUPPORTED_STATIONS: Set[str] = {"ST-001", "ST-002", "ST-003"}

    # Initial candidate mappings proposed by teammate (status: UNCONFIRMED_PROPOSAL)
    _PROPOSED_CANDIDATE_MAPPINGS: Dict[str, Dict[str, Any]] = {
        "STN-01": {
            "external_id": "ST-001",
            "caltech_source_id": "1-39-139-650",
            "status": MappingVerificationStatus.UNCONFIRMED_PROPOSAL,
            "notes": "Candidate mapping from EVCharge-Predict partner; physical station correspondence unconfirmed.",
        },
        "STN-02": {
            "external_id": "ST-002",
            "caltech_source_id": "1-39-139-651",
            "status": MappingVerificationStatus.UNCONFIRMED_PROPOSAL,
            "notes": "Candidate mapping from EVCharge-Predict partner; physical station correspondence unconfirmed.",
        },
        "STN-03": {
            "external_id": "ST-003",
            "caltech_source_id": "1-39-139-652",
            "status": MappingVerificationStatus.UNCONFIRMED_PROPOSAL,
            "notes": "Candidate mapping from EVCharge-Predict partner; physical station correspondence unconfirmed.",
        },
        "STN-04": {
            "external_id": None,
            "caltech_source_id": None,
            "status": MappingVerificationStatus.UNSUPPORTED_BY_MODEL,
            "notes": "Highway transit depot; not available in EVCharge-Predict 3-station model.",
        },
        "STN-05": {
            "external_id": None,
            "caltech_source_id": None,
            "status": MappingVerificationStatus.UNSUPPORTED_BY_MODEL,
            "notes": "Campus station; not available in EVCharge-Predict 3-station model.",
        },
    }

    _active_profile: Optional[str] = None
    _mappings: Dict[str, Dict[str, Any]] = {}
    _external_to_internal: Dict[str, str] = {}
    _internal_to_external: Dict[str, str] = {}

    @classmethod
    def _initialize(cls) -> None:
        """Initializes mapping tables from defaults if not already loaded."""
        if not cls._mappings:
            cls.reset_to_defaults()

    @classmethod
    def reset_to_defaults(cls) -> None:
        """Resets all mappings to the unconfirmed candidate proposals and configured profile."""
        cls._active_profile = getattr(settings, "STATION_INTEGRATION_PROFILE", "five_station_mock")
        cls._mappings = {}
        cls._external_to_internal = {}
        cls._internal_to_external = {}

        global_confirmed = getattr(settings, "CONFIRM_PHYSICAL_STATION_MAPPINGS", False)

        for int_id, data in cls._PROPOSED_CANDIDATE_MAPPINGS.items():
            status = data["status"]
            if global_confirmed and status == MappingVerificationStatus.UNCONFIRMED_PROPOSAL:
                status = MappingVerificationStatus.CONFIRMED_PHYSICAL

            cls._mappings[int_id] = {
                "external_id": data["external_id"],
                "caltech_source_id": data["caltech_source_id"],
                "status": status,
                "notes": data["notes"],
            }
            if data["external_id"]:
                cls._external_to_internal[data["external_id"]] = int_id
                cls._internal_to_external[int_id] = data["external_id"]

    @classmethod
    def get_profile(cls) -> str:
        cls._initialize()
        return cls._active_profile or "five_station_mock"

    @classmethod
    def set_profile(cls, profile_name: str) -> None:
        cls._initialize()
        valid_profiles = [p.value for p in IntegrationProfile]
        if profile_name not in valid_profiles:
            raise StationMappingError(
                f"Invalid station integration profile '{profile_name}'. Valid options: {valid_profiles}"
            )
        cls._active_profile = profile_name

    @classmethod
    def get_profile_stations(cls, profile_name: Optional[str] = None) -> List[str]:
        """Returns the internal station IDs active under the specified or current profile."""
        cls._initialize()
        prof = profile_name or cls.get_profile()
        if prof == IntegrationProfile.THREE_STATION_INTEGRATION.value:
            return ["STN-01", "STN-02", "STN-03"]
        return ["STN-01", "STN-02", "STN-03", "STN-04", "STN-05"]

    @classmethod
    def get_supported_predictor_stations(cls) -> List[str]:
        """Returns canonical external station IDs supported by the current EVCharge-Predict model."""
        return sorted(list(cls._PREDICTOR_SUPPORTED_STATIONS))

    @classmethod
    def is_physically_confirmed(cls, internal_id: str) -> bool:
        cls._initialize()
        entry = cls._mappings.get(internal_id)
        if not entry:
            return False
        return entry["status"] == MappingVerificationStatus.CONFIRMED_PHYSICAL

    @classmethod
    def confirm_mapping(cls, internal_id: str, external_id: str, caltech_source_id: Optional[str] = None) -> None:
        """Explicitly records that physical station correspondence has been verified."""
        cls._initialize()
        cls.register_mapping(
            internal_id=internal_id,
            external_id=external_id,
            caltech_source_id=caltech_source_id,
            is_confirmed=True,
        )

    @classmethod
    def register_mapping(
        cls,
        internal_id: str,
        external_id: str,
        caltech_source_id: Optional[str] = None,
        is_confirmed: bool = False,
        notes: str = "",
    ) -> None:
        """
        Registers a station mapping pair with ambiguity, duplication, and predictor support checks.
        Rejects missing, duplicate, or ambiguous mappings with clear StationMappingError.
        """
        cls._initialize()
        if not internal_id or not isinstance(internal_id, str):
            raise StationMappingError("Internal station ID must be a non-empty string.")
        if not external_id or not isinstance(external_id, str):
            raise StationMappingError("External station ID must be a non-empty string.")

        int_key = internal_id.strip()
        ext_key = external_id.strip()

        # Check for ambiguous / conflicting mapping registrations
        existing_ext = cls._internal_to_external.get(int_key)
        if existing_ext and existing_ext != ext_key:
            raise StationMappingError(
                f"Conflicting station mapping: internal station '{int_key}' is already mapped to '{existing_ext}'. "
                f"Cannot ambiguously remap to '{ext_key}'."
            )

        existing_int = cls._external_to_internal.get(ext_key)
        if existing_int and existing_int != int_key:
            raise StationMappingError(
                f"Conflicting station mapping: external station '{ext_key}' is already mapped to internal '{existing_int}'. "
                f"Cannot ambiguously map to '{int_key}'."
            )

        status = MappingVerificationStatus.CONFIRMED_PHYSICAL if is_confirmed else MappingVerificationStatus.UNCONFIRMED_PROPOSAL

        cls._mappings[int_key] = {
            "external_id": ext_key,
            "caltech_source_id": caltech_source_id,
            "status": status,
            "notes": notes or f"Custom mapping ({status.value})",
        }
        cls._internal_to_external[int_key] = ext_key
        cls._external_to_internal[ext_key] = int_key

    @classmethod
    def to_external(
        cls,
        internal_id: str,
        validate_predictor_support: bool = False,
        require_physical_confirmed: bool = False,
    ) -> str:
        """
        Translates an internal station ID to canonical external predictor station ID.

        Enforces:
        - Predictor model capability check (rejects STN-04 / STN-05 if validate_predictor_support is True).
        - Physical confirmation check (rejects unconfirmed mappings if require_physical_confirmed is True).
        """
        cls._initialize()
        if not internal_id or not isinstance(internal_id, str):
            raise StationMappingError(
                f"Invalid internal station ID '{internal_id}'. Must be a non-empty string."
            )

        station_key = internal_id.strip()

        # Check if already in canonical external format
        if station_key in cls._PREDICTOR_SUPPORTED_STATIONS:
            return station_key

        entry = cls._mappings.get(station_key)
        if not entry or not entry.get("external_id"):
            # Check if this station is known to be unsupported by the model
            if entry and entry.get("status") == MappingVerificationStatus.UNSUPPORTED_BY_MODEL:
                raise StationMappingError(
                    f"Station '{station_key}' is not supported by the EVCharge-Predict model. "
                    f"The current model only supports canonical stations {sorted(list(cls._PREDICTOR_SUPPORTED_STATIONS))}.",
                    station_id=station_key,
                )
            raise StationMappingError(
                f"Internal station ID '{station_key}' has no configured mapping to an external predictor station.",
                station_id=station_key,
            )

        ext_id = entry["external_id"]

        # Validate predictor model support
        if validate_predictor_support and ext_id not in cls._PREDICTOR_SUPPORTED_STATIONS:
            raise StationMappingError(
                f"Station '{station_key}' maps to external ID '{ext_id}' which is not supported by the "
                f"EVCharge-Predict model. Supported stations: {sorted(list(cls._PREDICTOR_SUPPORTED_STATIONS))}.",
                station_id=station_key,
            )

        # Enforce physical verification safeguard if required
        if require_physical_confirmed and entry["status"] != MappingVerificationStatus.CONFIRMED_PHYSICAL:
            raise StationMappingError(
                f"Physical station correspondence for proposed mapping '{station_key}' -> '{ext_id}' "
                f"(Caltech source ID: {entry.get('caltech_source_id')}) is UNCONFIRMED. "
                f"Explicit physical verification required before live allocation.",
                station_id=station_key,
            )

        return ext_id

    @classmethod
    def to_internal(
        cls,
        external_id: str,
        known_internal_ids: Optional[Set[str]] = None,
        require_physical_confirmed: bool = False,
    ) -> str:
        """
        Translates canonical external predictor station ID to internal station ID.
        Rejects unmapped, unknown, or unconfirmed station mappings.
        """
        cls._initialize()
        if not external_id or not isinstance(external_id, str):
            raise StationMappingError(
                f"Invalid external station ID '{external_id}'. Must be a non-empty string."
            )

        station_key = external_id.strip()

        # Check explicit mapped registry
        int_id = cls._external_to_internal.get(station_key)
        if int_id:
            entry = cls._mappings.get(int_id)
            if require_physical_confirmed and entry and entry["status"] != MappingVerificationStatus.CONFIRMED_PHYSICAL:
                raise StationMappingError(
                    f"Physical station correspondence for proposed mapping '{int_id}' -> '{station_key}' "
                    f"(Caltech source ID: {entry.get('caltech_source_id')}) is UNCONFIRMED. "
                    f"Explicit physical verification required before live allocation.",
                    station_id=station_key,
                )
            return int_id

        # If already an internal ID format and recognized
        if station_key in cls._mappings:
            return station_key

        if known_internal_ids and station_key in known_internal_ids:
            return station_key

        raise StationMappingError(
            f"External station ID '{external_id}' cannot be mapped to any internal station ID. "
            f"Expected canonical predictor station from {sorted(list(cls._PREDICTOR_SUPPORTED_STATIONS))} or registered mapping.",
            station_id=external_id,
        )

    @classmethod
    def map_external_list(cls, external_ids: List[str], require_physical_confirmed: bool = False) -> List[str]:
        return [cls.to_internal(ext_id, require_physical_confirmed=require_physical_confirmed) for ext_id in external_ids]

    @classmethod
    def map_internal_list(
        cls,
        internal_ids: List[str],
        validate_predictor_support: bool = False,
        require_physical_confirmed: bool = False,
    ) -> List[str]:
        return [
            cls.to_external(
                int_id,
                validate_predictor_support=validate_predictor_support,
                require_physical_confirmed=require_physical_confirmed,
            )
            for int_id in internal_ids
        ]

    @classmethod
    def get_all_mapping_details(cls) -> List[Dict[str, Any]]:
        """Returns structured metadata for all registered station mappings."""
        cls._initialize()
        details = []
        for int_id in sorted(cls._mappings.keys()):
            item = cls._mappings[int_id]
            details.append({
                "internal_id": int_id,
                "external_id": item["external_id"],
                "caltech_source_id": item["caltech_source_id"],
                "verification_status": item["status"].value if isinstance(item["status"], MappingVerificationStatus) else str(item["status"]),
                "is_physically_confirmed": item["status"] == MappingVerificationStatus.CONFIRMED_PHYSICAL,
                "supported_by_predictor_model": item["external_id"] in cls._PREDICTOR_SUPPORTED_STATIONS if item["external_id"] else False,
                "notes": item["notes"],
            })
        return details
