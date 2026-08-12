#!/usr/bin/env python3

import sys

from web3ai4io_dataset.collect_launchpads import main


if __name__ == "__main__":
    sys.argv.insert(1, "sunpump")
    main()
