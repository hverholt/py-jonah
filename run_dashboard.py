"""Launch the ADCP dashboard from the project root."""

import matplotlib

matplotlib.use("Agg")

from dashboard.app import main


if __name__ == "__main__":
    main()
