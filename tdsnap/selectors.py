"""Every TD Snap UI Automation identifier AAC Editor relies on (roadmap C10).

TD Snap's editing panel is the surface most likely to change in a product
update, and a renamed control used to be found by searching live.py for a
string. They are collected here so a new TD Snap version can be checked
against one list, and so session T3-1's findings have one place to land.

Names that are matched by text (window title, delete action names) stay
beside the code that interprets them; this module holds AutomationIds.
"""

WINDOW_NAME = "TD Snap"

DONE_BUTTON = "DoneButton"
SETTINGS_BUTTON = "settings_button"
UNDO_BUTTON = "UndoButton"
BACK_BUTTON = "BackButton"
PART_BACK_BUTTON = "PART_BackButton"
MESSAGE_BOX = "MessageBox"
LABEL_TEXT_BOX = "TextBox"
SYMBOL_SEARCH_BUTTON = "OpenSymbolSearchButton"
SYMBOL_QUERY_BUTTON = "QueryButton"
MEDIUM_ITEM = "MediumItem"
# UWP ContentDialog buttons: their presence means a dialog is open.
DIALOG_PRIMARY = "PrimaryButton"
DIALOG_SECONDARY = "SecondaryButton"

# TD Snap package versions on which the live path has been exercised on real
# hardware (doc 07, release statement). Empty until session T3-1 records one;
# any other version is reported as untested at connect.
TESTED_TDSNAP_VERSIONS: tuple = ()
