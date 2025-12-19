import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

app = Server("fusion-cad-server")

FUSION_URL = "http://localhost:8080"

# Helper to avoid repeating HTTP/error handling code
async def call_fusion_api(tool_name: str, params: dict, success_message: str) -> list[TextContent]:
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                FUSION_URL,
                json={
                    "tool": tool_name,
                    "params": params
                },
                timeout=10.0
            )

            response.raise_for_status()
            result = response.json()

            if result.get("status") == "success":
                return [TextContent(type="text", text=f"✅ {success_message}")]
            else:
                error_msg = result.get('message', 'Unknown error')
                return [TextContent(type="text", text=f"❌ Failed: {error_msg}")]

    except httpx.ConnectError:
        return [TextContent(
            type="text",
            text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
        )]
    except Exception as e:
        return [TextContent(type="text", text=f"❌ Error: {str(e)}")]

@app.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="create_rectangle",
            description="Create a rectangle in Fusion 360 on the XZ plane (top view). The rectangle will be positioned with one corner at (x, z) and extend in the positive X and Z directions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "length": {
                        "type": "number",
                        "description": "Length in cm (extends in positive Z direction - vertical)"
                    },
                    "width": {
                        "type": "number",
                        "description": "Width in cm (extends in positive X direction)"
                    },
                    "x": {
                        "type": "number",
                        "description": "X coordinate for the starting corner in cm. Defaults to 0 if not provided."
                    },
                    "z": {
                        "type": "number",
                        "description": "Z coordinate for the starting corner in cm (vertical position). Defaults to 0 if not provided."
                    }
                },
                "required": ["length", "width"]
            }
        ),
        # LINE TOOL
        Tool(
            name="sketch_line",
            description="Create a line in Fusion 360 on the XZ plane (top view). If xTwo and zTwo are not provided, the line will be drawn from the origin (0, 0) to (xOne, zOne). If all coordinates are provided, the line will be drawn from (xOne, zOne) to (xTwo, zTwo). DO NOT TRY CREATING A SHAPE TO BE EXTRUDED BY COMBINING MUTLIPLE LINE SKETCHES. CREATING MULTIPLES LINES TO CREATE A SHAPE, EVEN IF CLOSED, WILL STILL NOT ALLOW THE SHAPE TO BE EXTRUDED AND WILL CAUSE AN ERROR. SO DO NOT TRY CREATING AN OBJECT BY CONNECTING LINE AND EXTRUDING",
            inputSchema={
                "type": "object",
                "properties": {
                    "xOne": {
                        "type": "number",
                        "description": "X coordinate of the first point (or end point if xTwo/zTwo not provided) in cm"
                    },
                    "zOne": {
                        "type": "number",
                        "description": "Z coordinate of the first point (or end point if xTwo/zTwo not provided) in cm"
                    },
                    "xTwo": {
                        "type": "number",
                        "description": "X coordinate of the second point in cm. Optional - if not provided, line starts from origin."
                    },
                    "zTwo": {
                        "type": "number",
                        "description": "Z coordinate of the second point in cm. Optional - if not provided, line starts from origin."
                    }
                },
                "required": ["xOne", "zOne"]
            }
        ),
        # CIRCLE TOOL
        Tool(
            name="sketch_circle",
            description="Create a circle in Fusion 360 on the XZ plane (top view). You can specify either radius or diameter (at least one is required and must be non negative). The x and z coordinates specify the center of the circle and default to (0, 0) if not provided.",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {
                        "type": "number",
                        "description": "Radius of the circle in cm. Either radius or diameter must be provided."
                    },
                    "diameter": {
                        "type": "number",
                        "description": "Diameter of the circle in cm. Either radius or diameter must be provided."
                    },
                    "x": {
                        "type": "number",
                        "description": "X coordinate of the circle center in cm. Defaults to 0 if not provided."
                    },
                    "z": {
                        "type": "number",
                        "description": "Z coordinate of the circle center in cm. Defaults to 0 if not provided."
                    }
                },
                "required": []
            }
        ),
        # EXTRUDE TOOL
        Tool(
            name="extrude_profile",
            description="Extrude the most recent sketch to create a 3D body in Fusion 360. Must be called AFTER creating a sketch (like create_rectangle). The extrusion will be perpendicular to the sketch plane. Positive distance means extrusion in the positive Y (up) direction while negative distances means extrusion in the negative Y (down) direction",
            inputSchema={
                "type": "object",
                "properties": {
                    "distance": {
                        "type": "number",
                        "description": "Extrusion distance in cm. Must be between -1000 and 1000."
                    }
                },
                "required": ["distance"]
            }
        ),
        # EXTRUDE CUT TOOL
        Tool(
            name="extrude_cut",
            description="Extrude cut through existing bodies in Fusion 360. Must be called AFTER creating a sketch (like create_rectangle or sketch_circle). The sketch profile will be extruded and automatically cut through any bodies it intersects. The extrusion will be perpendicular to the sketch plane.",
            inputSchema={
                "type": "object",
                "properties": {
                    "distance": {
                        "type": "number",
                        "description": "Extrusion distance in cm. Must be greater than -1000 and less than 1000. This is how far the cut will extend. Positive distance meanns cutting in positive Y axis (up) while negatie distance means cutting in negative Y axis(down)"
                    }
                },
                "required": ["distance"]
            }
        ),
        # FILLET TOOL
        Tool(
            name="fillet_edges",
            description="Round all edges of the most recent 3D body in Fusion 360. Must be called AFTER creating a 3D body (via extrusion). All edges will be filleted with the same radius. FILLETS ALL EDGES",
            inputSchema={
                "type": "object",
                "properties": {
                    "radius": {
                        "type": "number",
                        "description": "Fillet radius in cm. Must be greater than 0 and less than 10."
                    }
                },
                "required": ["radius"]
            }
        ),
        # CHAMFER TOOL
        Tool(
            name="chamfer_edges",
            description="Chamfer (bevel) all edges of the most recent 3D body in Fusion 360. Must be called AFTER creating a 3D body (via extrusion). All edges will be chamfered with the specified distance and angle. CHAMFERS ALL EDGES",
            inputSchema={
                "type": "object",
                "properties": {
                    "distance": {
                        "type": "number",
                        "description": "Chamfer distance in cm. Must be greater than 0 and less then half of minimum dimension of the body (length, width, or extrusion distance). If the distance is too large relative to the geometry, the chamfer will fail. Recommended to use values less than half of the smallest body dimension."
                    },
                    "angle": {
                        "type": "number",
                        "description": "Chamfer angle in degrees. Defaults to 45 degrees if not provided. Common values: 30, 45, 60. Must be between 0 and 90 degrees."
                    }
                },
                "required": ["distance"]
            }
        ),
        # POLYLINE TOOL
        Tool(
            name="sketch_polyline",
            description="Create a polyline (connected line segments) in Fusion 360 on the XZ plane. Provide an array of points and they will be connected in order. If you want a closed polygon, make the last point equal to the first point.",
            inputSchema={
                "type": "object",
                "properties": {
                    "points": {
                        "type": "array",
                        "description": "Array of points to connect. Each point has x and z coordinates in cm.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "x": {
                                    "type": "number",
                                    "description": "X coordinate in cm"
                                },
                                "z": {
                                    "type": "number",
                                    "description": "Z coordinate in cm"
                                }
                            },
                            "required": ["x", "z"]
                        },
                        "minItems": 2
                    }
                },
                "required": ["points"]
            }
        ),
        # CLEAR TOOL
        Tool(
            name="clear_all",
            description="Clear all sketches and 3D bodies from the Fusion 360 design. This removes everything from the workspace, giving you a clean slate.",
            inputSchema={
                "type": "object",
                "properties": {},
                "required": []
            }
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    if name == "create_rectangle":
        length = arguments["length"]
        width = arguments["width"]
        x = arguments.get("x", 0)
        z = arguments.get("z", 0)

        # Build success message
        if x == 0 and z == 0:
            msg = f"Rectangle created: {length} cm x {width} cm at origin"
        else:
            msg = f"Rectangle created: {length} cm x {width} cm at ({x}, {z})"

        return await call_fusion_api(
            tool_name="sketchRectangle",
            params={"length": length, "width": width, "x": x, "z": z},
            success_message=msg
        )

    elif name == "sketch_line":
        x_one = arguments["xOne"]
        z_one = arguments["zOne"]
        x_two = arguments.get("xTwo")
        z_two = arguments.get("zTwo")

        # Build params - only include xTwo/zTwo if both are provided
        params = {"xOne": x_one, "zOne": z_one}
        if x_two is not None and z_two is not None:
            params["xTwo"] = x_two
            params["zTwo"] = z_two

        # Build success message
        if x_two is None or z_two is None:
            msg = f"Line created from origin (0, 0) to ({x_one}, {z_one})"
        else:
            msg = f"Line created from ({x_one}, {z_one}) to ({x_two}, {z_two})"

        return await call_fusion_api(
            tool_name="sketchLine",
            params=params,
            success_message=msg
        )

    elif name == "sketch_circle":
        radius = arguments.get("radius")
        diameter = arguments.get("diameter")
        x = arguments.get("x", 0)
        z = arguments.get("z", 0)

        # Validation
        if radius is None and diameter is None:
            return [TextContent(type="text", text="❌ Either radius or diameter must be provided")]

        if (radius is not None and radius < 0) or (diameter is not None and diameter < 0):
            return [TextContent(type="text", text="❌ Radius or diameter can't be negative")]

        # Build params
        params = {"x": x, "z": z}
        if radius is not None:
            params["radius"] = radius
        if diameter is not None:
            params["diameter"] = diameter

        # Build success message
        display_radius = radius if radius is not None else diameter / 2.0
        if x == 0 and z == 0:
            msg = f"Circle created at origin with radius {display_radius} cm"
        else:
            msg = f"Circle created at ({x}, {z}) with radius {display_radius} cm"

        return await call_fusion_api(
            tool_name="sketchCircle",
            params=params,
            success_message=msg
        )

    elif name == "extrude_profile":
        distance = arguments["distance"]

        # Validation
        if distance >= 100 or distance <= -100:
            return [TextContent(
                type="text",
                text=f"❌ Distance absolute value is too large. Can't be greater than 100 (you gave: {distance})"
            )]

        return await call_fusion_api(
            tool_name="extrude",
            params={"distance": distance},
            success_message=f"Extrusion created: {distance} cm tall, 3D body formed"
        )

    elif name == "extrude_cut":
        distance = arguments["distance"]

        # Validation
        if distance < -1000 or distance > 1000:
            return [TextContent(type="text", text=f"❌ Distance too large (you gave: {distance})")]

        return await call_fusion_api(
            tool_name="extrudeCut",
            params={"distance": distance},
            success_message=f"Extrude cut created: {distance} cm deep, cutting through intersecting bodies"
        )

    elif name == "fillet_edges":
        radius = arguments["radius"]

        # Validation
        if radius <= 0:
            return [TextContent(type="text", text=f"❌ Radius must be greater than 0 (you gave: {radius})")]

        return await call_fusion_api(
            tool_name="fillet",
            params={"radius": radius},
            success_message=f"Fillet applied to all edges: {radius} cm radius"
        )

    elif name == "chamfer_edges":
        distance = arguments["distance"]
        angle = arguments.get("angle", 45.0)

        # Validation
        if distance <= 0:
            return [TextContent(type="text", text=f"❌ Distance must be greater than 0 (you gave: {distance})")]

        if angle <= 0 or angle >= 90:
            return [TextContent(type="text", text=f"❌ Angle must be between 0 and 90 degrees (you gave: {angle})")]

        return await call_fusion_api(
            tool_name="chamfer",
            params={"distance": distance, "angle": angle},
            success_message=f"Chamfer applied to all edges: {distance} cm distance at {angle}°"
        )

    elif name == "sketch_polyline":
        points = arguments["points"]

        # Validation
        if len(points) < 2:
            return [TextContent(type="text", text="❌ Need at least 2 points to create a polyline")]

        return await call_fusion_api(
            tool_name="sketchPolyline",
            params={"points": points},
            success_message=f"Polyline created with {len(points)} points"
        )

    elif name == "clear_all":
        return await call_fusion_api(
            tool_name="clear",
            params={},
            success_message="Cleared all sketches and bodies from Fusion 360 workspace"
        )

    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())