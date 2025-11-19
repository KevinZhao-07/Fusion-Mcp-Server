"""This file acts as the main module for this script."""

import traceback
import adsk.core
import adsk.fusion
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading
# import adsk.cam

# Initialize the global variables for the Application and UserInterface objects.
app = adsk.core.Application.get()
ui  = app.userInterface

class FusionAPIHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        #hello
        try:


        



def run(_context: str):
    """This function is called by Fusion when the script is run."""

    try:
        # Your code goes here.
        ui.messageBox(f'"{app.activeDocument.name}" is the active Document.')
    except:  #pylint:disable=bare-except
        # Write the error message to the TEXT COMMANDS window.
        app.log(f'Failed:\n{traceback.format_exc()}')
