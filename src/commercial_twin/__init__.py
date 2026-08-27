from commercial_twin.schemas import (
    CommercialAction,
    CommercialState,
    CommercialTwinSnapshot,
    CompanyState,
    CustomerState,
    GeographicExposure,
    TwinCalibrationRecord,
    TwinReadinessReport,
    WorldState,
)


def __getattr__(name: str) -> object:
    """Load orchestrators lazily so domain schemas can import the base action contract."""
    if name == "CommercialTwin":
        from commercial_twin.twin import CommercialTwin

        return CommercialTwin
    if name == "TwinFactory":
        from commercial_twin.factory import TwinFactory

        return TwinFactory
    if name == "CustomerTwinFactory":
        from commercial_twin.population_factory import CustomerTwinFactory

        return CustomerTwinFactory
    raise AttributeError(name)


__all__ = [
    "CommercialAction",
    "CommercialState",
    "CommercialTwinSnapshot",
    "CompanyState",
    "CustomerState",
    "GeographicExposure",
    "TwinCalibrationRecord",
    "TwinReadinessReport",
    "WorldState",
    "CommercialTwin",
    "TwinFactory",
    "CustomerTwinFactory",
]
