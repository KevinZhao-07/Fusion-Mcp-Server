#!/usr/bin/env python3
"""
Fusion 360 MCP Server - Built step by step
"""

import asyncio
import httpx
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Step 1: Create the MCP server
# This is like saying "I'm creating a new tool that Claude can use"
app = Server("fusion-cad-server")

# The URL where your Fusion HTTP server is running
FUSION_URL = "http://localhost:8080"


# Step 2: Tell Claude what tools are available
# This function gets called when Claude asks "what tools do you have?"
@app.list_tools()
async def list_tools() -> list[Tool]:
    """
    This returns a list of tools that Claude can call.
    Think of it like a menu at a restaurant - you're showing what's available.

    IMPORTANT: We need to return Tool objects, not plain dictionaries!
    """
    return [
        Tool(
            name="create_rectangle",
            description="Create a rectangle in Fusion 360 on the XZ plane (top view). The rectangle will be positioned with one corner at (x, z) and extend in the positive X and Z directions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "length": {
                        "type": "number",
                        "description": "Length in cm (extends in positive X direction)"
                    },
                    "width": {
                        "type": "number",
                        "description": "Width in cm (extends in positive Z direction - vertical)"
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
        # SKETCH LINE TOOL - Create a line on the XZ plane
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
        # SKETCH CIRCLE TOOL - Create a circle on the XZ plane
        Tool(
            name="sketch_circle",
            description="Create a circle in Fusion 360 on the XZ plane (top view). You can specify either radius or diameter (at least one is required). The x and z coordinates specify the center of the circle and default to (0, 0) if not provided.",
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
        # EXTRUDE TOOL - Turn a 2D sketch into a 3D body
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
        # EXTRUDE CUT TOOL - Cut through existing bodies
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
        # FILLET TOOL - Round the edges of a 3D body
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
        # CHAMFER TOOL - Bevel the edges of a 3D body
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
        # CLEAR TOOL - Clear all sketches and bodies
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


# Step 3: Handle when Claude actually CALLS a tool
# This function gets called when Claude says "okay, create a rectangle with length=10, width=5"
@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """
    This is where the actual work happens.
    - name: which tool Claude wants to use (e.g., "create_rectangle")
    - arguments: the parameters Claude is passing (e.g., {"length": 10, "width": 5})

    IMPORTANT: We need to return TextContent objects, not plain dictionaries!
    """

    if name == "create_rectangle":
        length = arguments["length"]
        width = arguments["width"]
        x = arguments.get("x", 0)  # Default to 0 if not provided
        z = arguments.get("z", 0)  # Default to 0 if not provided

        # NOW: Actually call Fusion!
        # We'll make an HTTP POST request to your Fusion server
        try:
            # Create an HTTP client (async version)
            async with httpx.AsyncClient() as client:
                # Make the POST request
                # Remember: your Fusion server expects {"tool": "sketchRectangle", "params": {...}}
                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "sketchRectangle",
                        "params": {
                            "length": length,
                            "width": width,
                            "x": x,
                            "z": z
                        }
                    },
                    timeout=10.0  # Wait up to 10 seconds
                )

                # Check if it worked
                response.raise_for_status()  # Raises error if status code is 4xx or 5xx
                result = response.json()

                # Check the response from Fusion
                if result.get("status") == "success":
                    if x == 0 and z == 0:
                        return [TextContent(
                            type="text",
                            text=f"✅ Rectangle created in Fusion 360: {length} cm x {width} cm at origin (0, 0)"
                        )]
                    else:
                        return [TextContent(
                            type="text",
                            text=f"✅ Rectangle created in Fusion 360: {length} cm x {width} cm at position ({x}, {z})"
                        )]
                else:
                    return [TextContent(
                        type="text",
                        text=f"❌ Fusion error: {result.get('message', 'Unknown error')}"
                    )]

        except httpx.ConnectError:
            # This happens if Fusion server isn't running
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            # Any other error
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    elif name == "sketch_line":
        # Extract the parameters
        x_one = arguments["xOne"]
        z_one = arguments["zOne"]
        x_two = arguments.get("xTwo")
        z_two = arguments.get("zTwo")

        # Make the HTTP call to Fusion
        try:
            async with httpx.AsyncClient() as client:
                # Build params - only include xTwo/zTwo if both are provided
                params = {
                    "xOne": x_one,
                    "zOne": z_one
                }
                if x_two is not None and z_two is not None:
                    params["xTwo"] = x_two
                    params["zTwo"] = z_two

                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "sketchLine",
                        "params": params
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    if x_two is None or z_two is None:
                        return [TextContent(
                            type="text",
                            text=f"✅ Line created from origin (0, 0) to ({x_one}, {z_one})"
                        )]
                    else:
                        return [TextContent(
                            type="text",
                            text=f"✅ Line created from ({x_one}, {z_one}) to ({x_two}, {z_two})"
                        )]
                else:
                    error_msg = result.get('message', 'Unknown error')
                    return [TextContent(
                        type="text",
                        text=f"❌ Line creation failed: {error_msg}"
                    )]

        except httpx.ConnectError:
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    elif name == "sketch_circle":
        # Extract the parameters
        radius = arguments.get("radius")
        diameter = arguments.get("diameter")
        x = arguments.get("x", 0)
        z = arguments.get("z", 0)

        # Validation - at least one of radius or diameter must be provided
        if radius is None and diameter is None:
            return [TextContent(
                type="text",
                text="❌ Either radius or diameter must be provided"
            )]
        
        if radius < 0 or diameter < 0:
            return [TextContent(
                type="text",
                text="❌ Radius or diameter can't be negative"
            )]

        # Make the HTTP call to Fusion
        try:
            async with httpx.AsyncClient() as client:
                # Build params
                params = {
                    "x": x,
                    "z": z
                }
                if radius is not None:
                    params["radius"] = radius
                if diameter is not None:
                    params["diameter"] = diameter

                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "sketchCircle",
                        "params": params
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    # Calculate what to display
                    display_radius = radius if radius is not None else diameter / 2.0
                    if x == 0 and z == 0:
                        return [TextContent(
                            type="text",
                            text=f"✅ Circle created at origin with radius {display_radius} cm"
                        )]
                    else:
                        return [TextContent(
                            type="text",
                            text=f"✅ Circle created at ({x}, {z}) with radius {display_radius} cm"
                        )]
                else:
                    error_msg = result.get('message', 'Unknown error')
                    return [TextContent(
                        type="text",
                        text=f"❌ Circle creation failed: {error_msg}"
                    )]

        except httpx.ConnectError:
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    elif name == "extrude_profile":
        # Extract the distance parameter
        distance = arguments["distance"]

        if distance >= 100 or distance <= -100:
            return [TextContent(
                type="text",
                text=f"❌ Distance absolute value is too large. Can't be greater then 100 (you gave: {distance})"
            )]

        # Make the HTTP call to Fusion
        try:
            async with httpx.AsyncClient() as client:
                # Your Fusion server expects {"tool": "extrude", "params": {"distance": ...}}
                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "extrude",
                        "params": {
                            "distance": distance
                        }
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    return [TextContent(
                        type="text",
                        text=f"✅ Extrusion created: {distance} cm tall, 3D body formed"
                    )]
                else:
                    # Give helpful error message
                    error_msg = result.get('message', 'Unknown error')
                    return [TextContent(
                        type="text",
                        text=f"❌ Extrusion failed: {error_msg}\n\n"
                             f"Did you create a sketch first (like create_rectangle)?"
                    )]

        except httpx.ConnectError:
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    elif name == "extrude_cut":
        # Extract the distance parameter
        distance = arguments["distance"]

        # VALIDATION
        if distance < -1000 or distance > 1000:
            return [TextContent(
                type="text",
                text=f"❌ Distance too large (you gave: {distance})"
            )]

        # Make the HTTP call to Fusion
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "extrudeCut",
                        "params": {
                            "distance": distance
                        }
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    return [TextContent(
                        type="text",
                        text=f"✅ Extrude cut created: {distance} cm deep, cutting through intersecting bodies"
                    )]
                else:
                    # Give helpful error message
                    error_msg = result.get('message', 'Unknown error')
                    return [TextContent(
                        type="text",
                        text=f"❌ Extrude cut failed: {error_msg}\n\n"
                             f"Did you create a sketch first (like sketch_circle or create_rectangle)?"
                    )]

        except httpx.ConnectError:
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    elif name == "fillet_edges":
        # Extract the radius parameter
        radius = arguments["radius"]

        # VALIDATION - This is important for fillet!
        # If radius is too large, Fusion will fail
        if radius <= 0:
            return [TextContent(
                type="text",
                text=f"❌ Radius must be greater than 0 (you gave: {radius})"
            )]

        # Make the HTTP call to Fusion
        try:
            async with httpx.AsyncClient() as client:
                # Your Fusion server expects {"tool": "fillet", "params": {"radius": ...}}
                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "fillet",
                        "params": {
                            "radius": radius
                        }
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    return [TextContent(
                        type="text",
                        text=f"✅ Fillet applied to all edges: {radius} cm radius"
                    )]
                else:
                    # Fillet can fail for many reasons - give helpful error
                    error_msg = result.get('message', 'Unknown error')
                    return [TextContent(
                        type="text",
                        text=f"❌ Fillet failed: {error_msg}\n\n"
                             f"Common reasons:\n"
                             f"- No 3D body exists (did you extrude first?)\n"
                             f"- Radius is too large for the geometry\n"
                             f"- The body has no edges to fillet"
                    )]

        except httpx.ConnectError:
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    elif name == "chamfer_edges":
        # Extract the parameters
        distance = arguments["distance"]
        angle = arguments.get("angle", 45.0)  # Default to 45 degrees

        # VALIDATION
        if distance <= 0:
            return [TextContent(
                type="text",
                text=f"❌ Distance must be greater than 0 (you gave: {distance})"
            )]

        if angle <= 0 or angle >= 90:
            return [TextContent(
                type="text",
                text=f"❌ Angle must be between 0 and 90 degrees (you gave: {angle})"
            )]

        # Make the HTTP call to Fusion
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "chamfer",
                        "params": {
                            "distance": distance,
                            "angle": angle
                        }
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    return [TextContent(
                        type="text",
                        text=f"✅ Chamfer applied to all edges: {distance} cm distance at {angle}°"
                    )]
                else:
                    error_msg = result.get('message', 'Unknown error')
                    return [TextContent(
                        type="text",
                        text=f"❌ Chamfer failed: {error_msg}\n\n"
                             f"Common reasons:\n"
                             f"- No 3D body exists (did you extrude first?)\n"
                             f"- Distance is too large for the geometry\n"
                             f"- The body has no edges to chamfer"
                    )]

        except httpx.ConnectError:
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    elif name == "clear_all":
        # No parameters needed for clear
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    FUSION_URL,
                    json={
                        "tool": "clear",
                        "params": {}
                    },
                    timeout=10.0
                )

                response.raise_for_status()
                result = response.json()

                if result.get("status") == "success":
                    return [TextContent(
                        type="text",
                        text=f"✅ Cleared all sketches and bodies from Fusion 360 workspace"
                    )]
                else:
                    error_msg = result.get('message', 'Unknown error')
                    return [TextContent(
                        type="text",
                        text=f"❌ Clear failed: {error_msg}"
                    )]

        except httpx.ConnectError:
            return [TextContent(
                type="text",
                text="❌ Cannot connect to Fusion server. Is the Fusion HTTP server running?"
            )]
        except Exception as e:
            return [TextContent(
                type="text",
                text=f"❌ Error: {str(e)}"
            )]

    else:
        return [TextContent(
            type="text",
            text=f"Unknown tool: {name}"
        )]


# Step 4: Run the server
# This starts the server and keeps it running, waiting for Claude to talk to it
async def main():
    """
    This starts the MCP server using stdio (standard input/output).
    stdio means: Claude Desktop will talk to this program through text in/out
    """
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    # When you run "python server.py", this starts everything
    asyncio.run(main())