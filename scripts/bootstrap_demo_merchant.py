from __future__ import annotations

from commercial_twin.merchant_validation.service import build_demo_service


def main() -> None:
    service = build_demo_service()
    print(f"SYNTHETIC DEMO — NOT COMMERCIAL EVIDENCE: {service.merchant_id}")


if __name__ == "__main__":
    main()
