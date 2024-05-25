# Standard
import json
import os
# External
import pytz
from dotenv import load_dotenv  # (use python-dotenv)
# Internal
from shared import handle_error


class InputHandler:
    def __init__(self, args):
        self.args = args
        self.domain = None
        self.server_id = None
        self.start_date = None
        self.timezone = None
        self.user_aliases = None
        self.min_games_required = None
        self.last_days_threshold = None
        self.min_games_last_days = None
        self.discard_ties = None
        self.decay_enabled = None
        self.decay_amount = None
        self.grace_days = None
        self.max_decay_proportion = None
        self.default_sigma = None
        self.default_mu = None
        self.verbose_output = None
        self.top_x = None
        self.write_txt = None
        self.write_csv = None
        self.json_file = None

    def set_handler(self):

        try:
            load_dotenv()
        except Exception as load_dotenv_exception:
            handle_error(load_dotenv_exception, "Failed to load environment variables from .env file")

        # Inputs (override with command-line arguments if provided)
        self.domain = self.args.domain or os.getenv("DOMAIN")
        self.server_id = self.args.server_id or os.getenv("SERVER_ID")
        self.start_date = self.args.date_start or os.getenv("DATE_START")
        timezone_in = self.args.timezone or os.getenv("TIMEZONE")
        self.timezone = pytz.timezone(timezone_in)
        self.user_aliases = json.loads(os.getenv("ALIASED_PLAYERS"))

        self.min_games_required = self.args.min_games or int(os.getenv("MINIMUM_GAMES_REQUIRED"))
        self.last_days_threshold = self.args.last_days_threshold or int(os.getenv("LAST_DAYS_THRESHOLD"))
        self.min_games_last_days = self.args.min_games_last_days or int(os.getenv("MINIMUM_GAMES_LAST_DAYS"))
        self.top_x = self.args.top_x or int(os.getenv("TOP_X_CUTOFF"))

        self.discard_ties = self.args.discard_ties or os.getenv("DISCARD_TIES") == 'True'
        self.decay_enabled = self.args.decay_enabled or os.getenv("DECAY_ENABLED") == 'True'
        self.decay_amount = self.args.decay_amount or float(os.getenv("DECAY_AMOUNT"))
        self.grace_days = self.args.grace_days or int(os.getenv("DECAY_GRACE_DAYS"))
        self.max_decay_proportion = self.args.max_decay_proportion or float(os.getenv("MAX_DECAY_PROPORTION"))

        self.default_sigma = self.args.ts_default_sigma or float(os.getenv("TS_DEFAULT_SIGMA"))
        self.default_mu = self.args.ts_default_mu or float(os.getenv("TS_DEFAULT_MU"))

        self.verbose_output = self.args.verbose_output or os.getenv("VERBOSE_OUTPUT") == 'True'
        self.write_txt = self.args.write_txt or os.getenv("WRITE_TXT") == 'True'
        self.write_csv = self.args.write_csv or os.getenv("WRITE_CSV") == 'True'
        self.json_file = self.args.json_file or os.getenv("JSON_FILENAME")

    def get_settings(self):
        return {
            "domain": self.domain,
            "server_id": self.server_id,
            "start_date": self.start_date,
            "timezone": self.timezone,
            "user_aliases": self.user_aliases,
            "min_games_required": self.min_games_required,
            "last_days_threshold": self.last_days_threshold,
            "min_games_last_days": self.min_games_last_days,
            "discard_ties": self.discard_ties,
            "decay_enabled": self.decay_enabled,
            "decay_amount": self.decay_amount,
            "grace_days": self.grace_days,
            "max_decay_proportion": self.max_decay_proportion,
            "default_sigma": self.default_sigma,
            "default_mu": self.default_mu,
            "verbose_output": self.verbose_output,
            "top_x": self.top_x,
            "write_txt": self.write_txt,
            "write_csv": self.write_csv,
            "json_file": self.json_file
        }
