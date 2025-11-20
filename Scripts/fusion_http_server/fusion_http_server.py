import traceback
import adsk.core
import adsk.fusion
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading

# Initialize the global variables for the Application and UserInterface objects.
app = adsk.core.Application.get()
ui = app.userInterface

# This will store our HTTP server so we can stop it later
http_server = None

class FusionAPIHandler(BaseHTTPRequestHandler):
    """Handles incoming HTTP requests"""

    def do_POST(self):
        """This method is called whenever someone sends a POST request"""
        try:
            # 1. Read the request body (the JSON data sent to us)
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            # 2. Parse the JSON string into a Python dictionary
            request_data = json.loads(post_data.decode('utf-8'))

            # 3. Route to the correct tool
            tool = request_data["tool"]
            if(tool == "sketchRectangle"):
                length = request_data["params"]["length"]
                width = request_data["params"]["width"]

                # Get the active design and root component
                design = app.activeProduct
                rootComp = design.rootComponent

                # Create a sketch on the horizontal plane
                sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)

                # Define two corner points for the rectangle
                point1 = adsk.core.Point3D.create(0, 0, 0)
                point2 = adsk.core.Point3D.create(length, width, 0)

                # Create the rectangle using Fusion's built-in function
                lines = sketch.sketchCurves.sketchLines
                rectangle = lines.addTwoPointRectangle(point1, point2)

                app.log(f"Rectangle created: {length} x {width}")

            if(tool == "extrude"):
                distance = request_data["params"]["distance"]

                # Get the active design and root component
                design = app.activeProduct
                rootComp = design.rootComponent

                # Get all profiles from the most recent sketch
                sketch = rootComp.sketches.item(rootComp.sketches.count - 1)

                # Create a collection of profiles to extrude
                profiles = adsk.core.ObjectCollection.create()
                for profile in sketch.profiles:
                    profiles.add(profile)

                # Create an extrude feature
                extrudes = rootComp.features.extrudeFeatures
                extrudeInput = extrudes.createInput(profiles, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

                # Define the extrude distance
                distanceValue = adsk.core.ValueInput.createByReal(distance)
                extrudeInput.setDistanceExtent(False, distanceValue)

                # Create the extrude
                extrude = extrudes.add(extrudeInput)
                app.log(f"Extrude created: {distance} cm")

            if(tool == "fillet"):
                radius = request_data["params"]["radius"]

                # Get the active design and root component
                design = app.activeProduct
                rootComp = design.rootComponent

                # Get the last body created
                body = rootComp.bRepBodies.item(rootComp.bRepBodies.count - 1)

                # Get all edges from the body
                edges = adsk.core.ObjectCollection.create()
                for edge in body.edges:
                    edges.add(edge)

                # Create a fillet feature
                fillets = rootComp.features.filletFeatures
                filletInput = fillets.createInput()
                filletInput.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByReal(radius), True)

                # Create the fillet
                fillet = fillets.add(filletInput)
                app.log(f"Fillet created: {radius} cm radius")


            response = {
                "status": "success",
                "message": "plesae tell me you see this",
                "received": request_data
            }

            # 4. Send the response back
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))

        except Exception as e:
            # If something goes wrong, send an error response
            error_response = {"status": "error", "message": str(e)}
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode('utf-8'))

    def log_message(self, format, *args):
        """Override to prevent logging to console"""
        pass

def start_server():
    """Start the HTTP server in a background thread"""
    global http_server
    http_server = HTTPServer(('localhost', 8080), FusionAPIHandler)
    http_server.serve_forever()  # This keeps the server running

def run(context):
    """This function is called by Fusion when the script is run."""
    global http_server
    try:
        # Stop existing server if it's running
        if http_server:
            try:
                http_server.shutdown()
                app.log('Stopped previous server instance')
            except:
                pass

        # Start the server in a separate thread so it doesn't block Fusion
        server_thread = threading.Thread(target=start_server)
        server_thread.daemon = True  # Thread dies when Fusion closes
        server_thread.start()

        # Show success message AFTER starting thread
        ui.messageBox('Fusion HTTP Server started on port 8080!')
        app.log('hello')
    except Exception as e:
        ui.messageBox(f'Error: {str(e)}')
        app.log(f'Failed:\n{traceback.format_exc()}')

def stop(context):
    """This function is called by Fusion when the script is stopped."""
    global http_server
    if http_server:
        http_server.shutdown()
        ui.messageBox('Fusion HTTP Server stopped')
