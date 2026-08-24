from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from web3ai4io_dataset.build_events import main


if __name__ == "__main__":
    main()
