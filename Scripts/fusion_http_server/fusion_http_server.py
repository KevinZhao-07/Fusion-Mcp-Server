import traceback
import adsk.core
import adsk.fusion
from http.server import HTTPServer, BaseHTTPRequestHandler
import json
import threading

app = adsk.core.Application.get()
ui = app.userInterface

http_server = None

class FusionAPIHandler(BaseHTTPRequestHandler):

    def do_POST(self):
        try:
            # Read request body
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)

            # Parse JSON
            request_data = json.loads(post_data.decode('utf-8'))

            # Route to correct tool
            tool = request_data["tool"]
            if(tool == "sketchRectangle"):
                length = request_data["params"]["length"]
                width = request_data["params"]["width"]
                x = request_data["params"].get("x", 0)
                z = request_data["params"].get("z", 0)

                design = app.activeProduct
                rootComp = design.rootComponent

                # Sketch on XZ plane
                sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)

                # Two corner points
                point1 = adsk.core.Point3D.create(x, z, 0)
                point2 = adsk.core.Point3D.create(x + width, z + length, 0)

                # Draw rectangle
                lines = sketch.sketchCurves.sketchLines
                rectangle = lines.addTwoPointRectangle(point1, point2)

                app.log(f"Rectangle created: {width} x {length} at ({x}, {z})")

            if(tool == "sketchLine"):
                x_one = request_data["params"]["xOne"]
                z_one = request_data["params"]["zOne"]
                x_two = request_data["params"].get("xTwo", None)
                z_two = request_data["params"].get("zTwo", None)

                design = app.activeProduct
                rootComp = design.rootComponent

                sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)

                # Line from origin if xTwo/zTwo not provided
                if x_two is None or z_two is None:
                    point1 = adsk.core.Point3D.create(0, 0, 0)
                    point2 = adsk.core.Point3D.create(x_one, z_one, 0)
                    app.log(f"Line created from origin (0, 0) to ({x_one}, {z_one})")
                else:
                    point1 = adsk.core.Point3D.create(x_one, z_one, 0)
                    point2 = adsk.core.Point3D.create(x_two, z_two, 0)
                    app.log(f"Line created from ({x_one}, {z_one}) to ({x_two}, {z_two})")

                lines = sketch.sketchCurves.sketchLines
                line = lines.addByTwoPoints(point1, point2)

            if(tool == "sketchCircle"):
                radius = request_data["params"].get("radius", None)
                diameter = request_data["params"].get("diameter", None)
                x = request_data["params"].get("x", 0)
                z = request_data["params"].get("z", 0)

                # Convert diameter to radius if needed
                if radius is None and diameter is not None:
                    radius = diameter / 2.0
                elif radius is None and diameter is None:
                    raise Exception("Either radius or diameter must be provided")

                design = app.activeProduct
                rootComp = design.rootComponent

                sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)

                center = adsk.core.Point3D.create(x, z, 0)

                circles = sketch.sketchCurves.sketchCircles
                circle = circles.addByCenterRadius(center, radius)

                app.log(f"Circle created: radius {radius} cm at ({x}, {z})")

            if(tool == "extrude"):
                distance = request_data["params"]["distance"]

                design = app.activeProduct
                rootComp = design.rootComponent

                # Grab most recent sketch
                sketch = rootComp.sketches.item(rootComp.sketches.count - 1)

                # Get the closed profile
                if sketch.profiles.count > 0:
                    profile = sketch.profiles.item(0)
                else:
                    raise Exception("No profile found in sketch")

                extrudes = rootComp.features.extrudeFeatures
                extrudeInput = extrudes.createInput(profile, adsk.fusion.FeatureOperations.NewBodyFeatureOperation)

                distanceValue = adsk.core.ValueInput.createByReal(distance)
                extrudeInput.setDistanceExtent(False, distanceValue)

                extrude = extrudes.add(extrudeInput)
                app.log(f"Extrude created: {distance} cm")

            if(tool == "extrudeCut"):
                distance = request_data["params"]["distance"]

                design = app.activeProduct
                rootComp = design.rootComponent

                sketch = rootComp.sketches.item(rootComp.sketches.count - 1)

                if sketch.profiles.count > 0:
                    profile = sketch.profiles.item(0)
                else:
                    raise Exception("No profile found in sketch")

                extrudes = rootComp.features.extrudeFeatures
                extrudeInput = extrudes.createInput(profile, adsk.fusion.FeatureOperations.CutFeatureOperation)

                distanceValue = adsk.core.ValueInput.createByReal(distance)
                extrudeInput.setDistanceExtent(False, distanceValue)

                # Automatically cuts any intersecting bodies
                extrude = extrudes.add(extrudeInput)
                app.log(f"Extrude cut created: {distance} cm")

            if(tool == "fillet"):
                radius = request_data["params"]["radius"]

                design = app.activeProduct
                rootComp = design.rootComponent

                # Grab last body
                body = rootComp.bRepBodies.item(rootComp.bRepBodies.count - 1)

                # Collect all edges
                edges = adsk.core.ObjectCollection.create()
                for edge in body.edges:
                    edges.add(edge)

                fillets = rootComp.features.filletFeatures
                filletInput = fillets.createInput()
                filletInput.addConstantRadiusEdgeSet(edges, adsk.core.ValueInput.createByReal(radius), True)

                fillet = fillets.add(filletInput)
                app.log(f"Fillet created: {radius} cm radius")

            if(tool == "chamfer"):
                distance = request_data["params"]["distance"]
                angle = request_data["params"].get("angle", 45.0)

                design = app.activeProduct
                rootComp = design.rootComponent

                body = rootComp.bRepBodies.item(rootComp.bRepBodies.count - 1)

                edges = adsk.core.ObjectCollection.create()
                for edge in body.edges:
                    edges.add(edge)

                chamfers = rootComp.features.chamferFeatures
                chamferInput = chamfers.createInput(edges, True)

                chamferInput.setToDistanceAndAngle(
                    adsk.core.ValueInput.createByReal(distance),
                    adsk.core.ValueInput.createByString(f"{angle} deg")
                )

                chamfer = chamfers.add(chamferInput)
                app.log(f"Chamfer created: {distance} cm distance at {angle} degrees")

            if(tool == "sketchPolyline"):
                points = request_data["params"]["points"]

                design = app.activeProduct
                rootComp = design.rootComponent

                sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)
                lines = sketch.sketchCurves.sketchLines

                for i in range(len(points) - 1):
                    current = points[i]
                    next_point = points[i + 1]

                    pt1 = adsk.core.Point3D.create(current["x"], current["z"], 0)
                    pt2 = adsk.core.Point3D.create(next_point["x"], next_point["z"], 0)

                    lines.addByTwoPoints(pt1, pt2)

                app.log(f"Polyline created with {len(points)} points, {len(points)-1} line segments")

            if(tool == "clear"):
                design = app.activeProduct
                rootComp = design.rootComponent

                # Delete all bodies (backwards to avoid index issues)
                bodies_count = rootComp.bRepBodies.count
                for i in range(bodies_count - 1, -1, -1):
                    body = rootComp.bRepBodies.item(i)
                    body.deleteMe()

                # Delete all sketches
                sketches_count = rootComp.sketches.count
                for i in range(sketches_count - 1, -1, -1):
                    sketch = rootComp.sketches.item(i)
                    sketch.deleteMe()

                app.log(f"Cleared {bodies_count} bodies and {sketches_count} sketches")

            response = {
                "status": "success",
                "received": request_data
            }

            # Send response
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))

        except Exception as e:
            error_response = {"status": "error", "message": str(e)}
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(error_response).encode('utf-8'))

    def log_message(self, format, *args):
        # Suppress console logging
        pass

def start_server():
    global http_server
    http_server = HTTPServer(('localhost', 8080), FusionAPIHandler)
    http_server.serve_forever()

def run(context):
    global http_server
    try:
        # Stop existing server if running
        if http_server:
            try:
                http_server.shutdown()
                http_server.server_close()
                http_server = None
                app.log('Stopped previous server instance')
            except Exception as e:
                app.log(f'Error stopping server: {e}')

        # Start server in background thread
        server_thread = threading.Thread(target=start_server)
        server_thread.daemon = True
        server_thread.start()

        ui.messageBox('Fusion HTTP Server started on port 8080!')
        app.log('Thread started')
    except Exception as e:
        ui.messageBox(f'Error: {str(e)}')
        app.log(f'Failed:\n{traceback.format_exc()}')

def stop(context):
    global http_server
    if http_server:
        http_server.shutdown()
        http_server.server_close()
        http_server = None
        ui.messageBox('Fusion HTTP Server stopped')