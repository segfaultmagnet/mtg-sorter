#!/usr/bin/env python

# Name:         mtgs_getprices.py
# Authors:      Geoff, Matthew Sheridan
# Date:         04 October 2012
# Revision:     23 April 2016
# Copyright:    (c) Geoff 2012
# Licence:      <your licence>

"""Retrieves current price data for MTG cards by scraping magiccards.info"""

__authors__ = "Geoff, Matthew Sheridan"
__credits__ = ["Geoff", "Matthew Sheridan"]
__date__    = "01 May 2016"
__version__ = "0.4e"
__status__  = "Development"

import os
import sys
import codecs
import copy
import csv
from datetime import datetime
import re
import traceback
from mtgs_card import MTGCard
from mtgs_error import *
from mtgs_json import MTGJson
from mtgs_webrenderer import WebRenderer
from configobj import ConfigObj

class GetPrices:
    global CONFIG_FILENAME
    global FORMATS
    global FORMATS_HEADERS
    global SEARCH_PATTERN
    CONFIG_FILENAME = "conf/conf.ini"
    FORMATS = ["deckstats", "excel"]
    FORMATS_HEADERS = [["amount", "card_name", "is_foil", "is_pinned", "set_id"],
                       ["CARD NAME", "QTY", "SET", "LOW (ea.)", "MID (ea.)", "HI (ea.)", "LOW", "MID", "HI"]]
    SEARCH_PATTERN = "TCGPPriceLow\".*\$(\d*.\d\d).*TCGPPriceMid.*\$(\d*.\d\d).*TCGPPriceHigh[^\$]*\$(\d*.\d\d)"

    def _defaults(self):
        """Set default values."""
        self._debug = False

        self._cwd = os.path.normpath(os.getcwd())
        self._debug_path   = ""

        self._read_format  = ""
        self._write_format = ""

        self._set_defs = None
        self._json_set = None

        self._count   = 0
        self._count_success = 0
        self._count_failed  = 0
        self._total_price_lo  = 0
        self._total_price_mid = 0
        self._total_price_hi  = 0

    def _convert_setcode(self, code, in_type, out_type="setCode"):
        """Converts set codes. Currently only does deckstats to setCode.

        Args:
            code      The code to convert.
            in_type   The type of code to convert.
            out_type  The type of code to return. [default="setCode"]

        Returns:
            Converted set code of type specified by out_type.
        """
        new_code = ""
        cols = {
            "name": 0,
            "setCode": 1,
            "gathererCode": 2,
            "oldCode": 3,
            "magicCardsInfoCode": 4,
            "deckstatsCode": 5
        }
        if not in_type in cols:
            raise Error("Invalid set type conversion: " + in_type)
        if not out_type in cols:
            raise Error("Invalid set type conversion: " + out_type)

        in_col = cols[in_type]
        out_col = cols[out_type]
        for row in self._set_defs:
            if row[in_col] == code:
                new_code = row[out_col]
        return new_code

    def _load_set_defs(self, path):
        """Retrives set definitions used to translate set identifiers, formatted same as set_defs.

        Args:
            path  string; File path to definition file set_defs.csv.

        Returns:
            Returns list of conversion lists.
        """
        dat = []
        try:
            with open(path, "r") as file:
                # Check for header row.
                header = csv.Sniffer().has_header(str(file.read(1024)))
                file.seek(0)
                if header:
                    next(file)
                reader = csv.reader(file, dialect="excel")
                for row in reader:
                    dat.append(row)
        except Error as e:
            raise e
        return dat

    def _path(self, file):
        """Returns full path of a file in the current working directory."""
        return os.path.normpath(self._cwd + "/" + file)

    def _print_debug(self, msg):
        """Appends debugging info to debug file."""
        if self._debug:
            timestamp = datetime.now()
            with open(self._debug_path, "a") as file:
                for line in msg.split("\n"):
                    file.write(str(timestamp) + ": " + line + "\n")

    def _print_error(self, err, help=False):
        """Prints error message.

        Args:
            msg   string; Error message to print.
            help  bool; Print help message yes/no.
        """
        print(err)
        if help:
            print("\n" + str(__doc__)[:-2])

    def get_prices(self, input_path, output_path, overwrite=False):
        """Conduct full read in, scrape, and write out.

        Args:
            input_path   string; File path to read the list of cards from.
            output_path  string; File path to write the list of cards to.
            overwrite    bool; Idicates whether path should be overwritten or
                         appended.
        """
        self._count         = 0
        self._count_total   = 0
        self._count_success = 0
        self._count_failed  = 0
        self._list_failed = []
        self._total_price_lo  = 0
        self._total_price_mid = 0
        self._total_price_hi  = 0
        input_rows  = []
        output_rows = []
        try:
            input_rows  = self.read_cards(input_path)
            output_rows = self.scrape(input_rows)
        except Error as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print(e)
            traceback.print_tb(exc_traceback, file=sys.stdout)
        except Exception as e:
            exc_type, exc_value, exc_traceback = sys.exc_info()
            print(type(e))
            traceback.print_tb(exc_traceback, file=sys.stdout)
        finally:
            self.write_cards(output_path, output_rows, overwrite)

    def read_cards(self, path):
        """Reads from file the list of cards to get prices for.

        Args:
            path  string; File path to read the list of cards from.

        Returns:
            A list of cards and quantities.
        """
        dat = []
        if not os.path.isfile(path):
            raise InvalidFileError(path)

        with open(path, "r", encoding="utf-8") as file:
            self._print_debug("Reading from " + path)
            # Check for header row.
            header = csv.Sniffer().has_header(str(file.read(1024)))
            file.seek(0)
            if header:
                next(file)

            reader = csv.reader(file, dialect="excel")
            for row in reader:
                name = row[1]
                qty  = row[0]
                setCode = self._convert_setcode(row[4], "deckstatsCode")
                match   = self._json_set.find_card(name, setCode)
                if match:
                    dat.append([match, qty])
                else:
                    self._print_debug("Could not match " + repr(name) +
                                      " in set " + repr(setCode))
                    self._count_failed += 1
                    self._list_failed.append([name, setCode])
                    # Try partial match w/ most recent set.

        if len(dat) < 1:
            raise ZeroLengthOutputError
        self._count = len(dat)

        return dat

    def scrape(self, input_rows):
        """Scrapes magiccards.info for card prices.

        Args:
            input_rows  array; The list of card names, quantities, and set identifiers to search for.

        Returns:
            A list of card names, quantities, sets, and prices for each.
            Prints progress to console.
        """
        renderer = WebRenderer(sys.argv)
        dat = []
        counter = 0

        sys.stdout.write("Fetching...")
        sys.stdout.flush()
        regex = re.compile(SEARCH_PATTERN)

        try:
            for row in input_rows:
                counter += 1
                card = row[0]
                qty  = int(row[1])
                self._count_total += qty
                mci_code = self._convert_setcode(card["setCode"],
                                                 in_type="setCode",
                                                 out_type="magicCardsInfoCode")
                output_row = []
                hit = False

                # Construct card url or query string, as appropriate.
                url = ""
                if mci_code:
                    if card["number"]:
                        url = ("http://magiccards.info/" + mci_code + "/en/" +
                               card["number"] + ".html")
                    else:
                        url = ("http://magiccards.info/query?q=" + "\"" +
                               card["name"] + "\" e:" + mci_code + "/en")
                else:
                    url = ("http://magiccards.info/query?q=" + "\"" +
                           card["name"] + "\"")

                result = str(renderer.render(url))
                prices = regex.search(result)

                # If match was found, add its data to output.
                if prices:
                    hit = True
                    self._count_success += 1
                    total_price_lo  = float(prices.group(1)) * qty
                    total_price_mid = float(prices.group(2)) * qty
                    total_price_hi  = float(prices.group(3)) * qty
                    output_row = [card["name"], qty, card["setCode"],
                                  prices.group(1), prices.group(2), prices.group(3),
                                  total_price_lo, total_price_mid, total_price_hi]
                    self._total_price_lo  += total_price_lo
                    self._total_price_mid += total_price_mid
                    self._total_price_hi += total_price_hi
                else:
                    self._count_failed += 1
                    output_row = [card["name"], qty, card["setCode"]]
                    self._list_failed.append([card["name"], card["setCode"]])

                # Display running progress.
                sys.stdout.write("\rFetching... (" + str(counter) + "/" +
                                  str(self._count) + ")")
                sys.stdout.flush()

                self._print_debug(str(counter) + "/" + str(self._count) +
                                  "  " + ["Miss: ", "Hit:  "][hit] +
                                  card["name"] + " (" + card["setCode"] + ")"
                                  "\n\t" + url)

                # Push last result onto results.
                dat.append(output_row)

        except (KeyboardInterrupt, SystemExit):
            raise InterruptedScrapeError
        except Exception as e:
            print("\n" + str(e))
            raise Error(e)
        finally:
            print("")
            # Total prices for each of the three columns.
            dat.append(["TOTAL", self._count_total, "", "", "", "",
                        round(self._total_price_lo, 2),
                        round(self._total_price_mid, 2),
                        round(self._total_price_hi, 2)])
            return dat

        return dat

    # Writes to file the cards and corresponding prices.
    def write_cards(self, path, output, overwrite=False):
        """Args:
            path       string; File path to write the list of cards to.
            output     array; The list of rows containing cards and prices.
            overwrite  bool; Idicates whether path should be overwritten or
                       appended.
        """

        if overwrite:
            write_mode = "w"
        else:
            write_mode = "a"

        with open(path, write_mode, newline='') as file:
            writer = csv.writer(file, dialect="excel")

            # Add header line if file is empty.
            if os.stat(path).st_size < 1:
                output.insert(0, FORMATS_HEADERS[1])

            for row in output:
                writer.writerow(row)

        print("Wrote to " + path)
        self._print_debug("Wrote to " + path)

    def summary(self):
        """Returns summary of last scrape attempt."""
        success = "Found:  " + str(self._count_success) + " card(s)."
        failed  = "Missed: " + str(self._count_failed)  + " card(s):"

        for miss in self._list_failed:
            failed += "\n  " + repr(miss[0]) + " (" + repr(miss[1]) + ")"

        if self._count_success and self._count_failed:
            return success + "\n" + failed
        elif self._count_success:
            return success
        elif self._count_failed:
            return failed
        return "No cards searched for."

    def __init__(self, debug=None):
        # Load configuration file info. Make these global later:
        config = ConfigObj(CONFIG_FILENAME)
        config_files  = config["files"]
        config_format = config["format"]

        self._defaults()
        self._debug = debug
        self._debug_path = self._path(config_files["debug"])

        set_defs_path = self._path(config_files["set_defs"])
        set_data_path = self._path(config_files["json_sets"])

        # Check for errors!
        try:
            if not os.path.isfile(set_defs_path):
                raise InvalidFileError(set_defs_path)
            if not os.path.isfile(set_data_path):
                raise InvalidFileError(set_data_path)
        except Error as e:
            _print_error(e, True)
            exit(1)

        self._set_defs = self._load_set_defs(set_defs_path)
        self._json_set = MTGJson(set_data_path)
