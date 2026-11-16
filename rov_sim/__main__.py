"""Module entry point for the ROV simulator."""
from rov_sim.cli import main


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Stopped by user.")
