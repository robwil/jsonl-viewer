"""Color pair constants and initialization."""

import curses

CP_USER_NAME = 1
CP_CHAR_NAME = 2
CP_SYSTEM_NAME = 3
CP_REASONING = 4
CP_SWIPE_INDICATOR = 5
CP_HELP_BAR = 6
CP_SEPARATOR = 7
CP_TIMESTAMP = 8
CP_CURSOR_MARKER = 9
CP_TITLE_BAR = 10
CP_PROGRESS_FILL = 11
CP_META = 12
CP_SEARCH_MATCH = 13


def init_colors():
    curses.start_color()
    curses.use_default_colors()
    curses.init_pair(CP_USER_NAME, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_CHAR_NAME, curses.COLOR_CYAN, -1)
    curses.init_pair(CP_SYSTEM_NAME, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_REASONING, curses.COLOR_MAGENTA, -1)
    curses.init_pair(CP_SWIPE_INDICATOR, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_HELP_BAR, curses.COLOR_BLACK, curses.COLOR_WHITE)
    curses.init_pair(CP_SEPARATOR, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_TIMESTAMP, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_CURSOR_MARKER, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_TITLE_BAR, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(CP_PROGRESS_FILL, curses.COLOR_BLACK, curses.COLOR_CYAN)
    curses.init_pair(CP_META, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_SEARCH_MATCH, curses.COLOR_RED, -1)
