# Design Decisions and Notes

## Architecture Decisions

### Two-Server Architecture

I chose to split the system into two separate servers rather than embedding everything in Fusion:

1. **Fusion HTTP Server** (runs inside Fusion 360)
   - Simple HTTP server using Python's built-in `http.server`
   - Lives in Fusion's scripting environment
   - Has direct access to Fusion API

2. **MCP Server** (standalone Python process)
   - Communicates with Claude Desktop via stdio
   - Makes HTTP calls to Fusion server
   - Isolated from Fusion's environment

**Why this approach?**

- **Separation of concerns:** MCP protocol handling is separate from CAD operations
- **Easier debugging:** Can test Fusion HTTP server independently with curl
- **Better error handling:** MCP server can catch connection errors and give helpful messages
- **Simpler Fusion code:** The Fusion script doesn't need to understand MCP protocol
- **Future flexibility:** Could swap out Fusion for another CAD program by replacing just the HTTP server

**Tradeoffs:**

- Extra network hop (stdio → HTTP → Fusion API)
- Need to manage two processes
- More complex setup for end users
- Limits cloud deployment (Fusion scripts must run locally)

I considered embedding the MCP server inside Fusion, but:
- Fusion's Python environment is restrictive
- Installing MCP SDK dependencies in Fusion is difficult
- stdio communication from within Fusion is problematic

### Tool Design

**Current tools:** `create_rectangle`, `sketch_line`, `sketch_circle`, `extrude_profile`, `extrude_cut`, `fillet_edges`, `chamfer_edges`, `clear_all`

These were chosen to demonstrate a complete workflow: 2D sketch → 3D body → finishing operations → cleanup.

**Development approach:**
- Implemented easiest tools first and tested them fully before moving to next
- Easier to weed out bugs and iterate faster
- Build confidence in the architecture before adding complexity

**Coordinate System:**
- X-axis: left ↔ right
- Y-axis: up ↔ down (vertical)
- Z-axis: forward ↔ back (depth)

**Plane System:**
- XZ plane (top view): X and Z vary, Y constant - **default for all sketch tools**
- XY plane (front view): X and Y vary, Z constant
- YZ plane (side view): Y and Z vary, X constant

All sketches currently default to the XZ plane. Users can position sketches at different depths using the Y coordinate, but the sketch itself remains on the XZ plane.

**Point3D Order:**
All tools consistently use `Point3D.create(x, y, z)` - the standard order of X, Y, Z coordinates.

**Validation ranges:**
- Length/width: Any positive value (no strict upper limit)
- Extrude distance: 0 < x < 1000 cm
- Fillet radius: 0 < x < 10 cm
- Chamfer distance: 0 < x < min(dimensions)/2 (with validation help in description)

### Async and HTTP Communication

**Using async/await and httpx:**
- Allows for asynchronous actions, prevents blocking and being held up
- HTTP requests don't freeze the MCP server
- Better user experience with non-blocking I/O

**Key insight:** Only I/O operations need `await` (HTTP requests, file operations). Data processing (JSON parsing, validation checks) is synchronous and doesn't need `await`.

### Error Handling

**Using try/except blocks:**
- Can run a block of code and handle exceptions gracefully
- Provides better error messages than crashes

**Three layers of error handling:**

1. **MCP Server validation** (server.py)
   - Checks parameter types and ranges
   - Returns friendly error messages
   - Happens before HTTP call (faster feedback)

2. **HTTP errors** (connection, timeout)
   - Caught by `httpx` exception handlers
   - Returns helpful diagnostic messages
   - Tells users how to fix common issues
   - 10-second timeout prevents indefinite waiting

3. **Fusion API errors** (fusion_http_server.py)
   - Wrapped in try/except
   - Returns 500 status with error details
   - Example: "No closed profile found in sketch"

**Why three layers?**
- Catches different types of failures
- Each layer has different information available
- Provides actionable error messages at each level

**Improved error messages:**
- Extrude operations now specify when profiles aren't found
- Clear explanation that multiple sketch_line calls create separate sketches
- Warnings about closed shapes being required for extrusion

### Stateful Operations

The Fusion HTTP server is **stateful** - it operates on "the most recent" sketch or body:

```python
# Get the most recent sketch
sketch = rootComp.sketches.item(rootComp.sketches.count - 1)

# Get the last body created
body = rootComp.bRepBodies.item(rootComp.bRepBodies.count - 1)
```

**Why this approach?**
- Simple: No need to track IDs or references
- Matches user mental model: "create this, then extrude it"
- Works for linear workflows (which is what Claude does)

**Limitations:**
- Can't operate on arbitrary shapes
- Breaks if user manually creates geometry between tool calls
- Can't go back and modify earlier steps
- Only works with one design at a time

**Better alternatives (for production):**
- Return object IDs and let tools reference them
- Use named references or tags
- Implement a command history/undo system

### Communication Format

**HTTP POST with JSON:**
```json
{
  "tool": "sketchRectangle",
  "params": {
    "length": 10,
    "width": 10,
    "x": 0,
    "y": 0,
    "z": 0
  }
}
```

**Why JSON over REST?**
- Simple single-endpoint design
- Tool name in payload (not URL path)
- Easy to extend with new tools
- Matches how MCP sends tool calls

**Alternative considered:** REST-style routes like `POST /sketch/rectangle`
- Rejected: More complex routing, harder to implement in basic HTTP server

### Units

**All dimensions in centimeters (cm)**

- Fusion's internal unit is cm
- No conversion needed
- Documented in tool descriptions
- Consistent across all tools

**Alternative:** Could accept units as parameters (`length: 10, units: "cm"`)
- Rejected: Adds complexity, cm is fine for current scope

## Current Implementation Details

### 3D Positioning

All sketch tools now support full 3D positioning with x, y, z coordinates:
- **Rectangle**: Can be positioned anywhere in 3D space using (x, y, z) for the starting corner
- **Line**: Both endpoints support full 3D coordinates (xOne, yOne, zOne) and (xTwo, yTwo, zTwo)
- **Circle**: Center can be positioned anywhere using (x, y, z)

By default, all coordinates default to 0 if not provided, placing shapes at the origin.

### Sketch Line Limitations

Each `sketch_line` call creates a **separate sketch**. This means:
- Multiple lines cannot be extruded together, even if they form a closed shape
- Users must use `create_rectangle` or `sketch_circle` for extrudable closed shapes
- This is explicitly documented in the tool description to guide Claude

### Multiple Operations

**Fillet and Chamfer** operate on ALL edges:
```python
for edge in body.edges:
    edges.add(edge)
```

This is clearly documented in tool descriptions with "FILLETS ALL EDGES" and "CHAMFERS ALL EDGES" warnings.

## Known Limitations

### 1. Single Construction Plane

All sketch tools currently use the XZ construction plane:
```python
sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)
```

**Impact:**
- Limited to top-down view sketching
- Can position sketches at different Y depths, but all sketches are parallel to XZ plane
- Can't easily create perpendicular features without manual Fusion manipulation

**Workaround:** Users can specify coordinates to position shapes, but they're always on the XZ plane.

### 2. No Edge Selection

Fillet and chamfer tools apply to ALL edges with the same parameters:
- Can't select specific edges
- Can't use different radii/distances for different edges
- All-or-nothing approach

**Impact:** Works for simple shapes, limiting for complex designs requiring selective edge treatment.

### 3. Sketch Line Cannot Create Extrudable Shapes

Each `sketch_line` call creates a separate sketch:
```python
# Each call creates a new sketch
sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)
```

**Impact:**
- Cannot draw triangles, pentagons, or custom polygons for extrusion
- Users must rely on rectangles and circles for extrudable shapes
- Major limitation for creating complex geometry

### 4. Profile Selection

Extrude operations always use the first profile in the most recent sketch:
```python
profile = sketch.profiles.item(0)
```

**Impact:**
- If a sketch has multiple closed regions, only the first is extruded
- Can't choose which profile to extrude from multi-profile sketches
- No way to extrude inner regions separately (like holes)

### 5. No Object References

All operations work on "most recent" objects:
- Most recent sketch for extrusion
- Most recent body for fillet/chamfer

**Impact:**
- Can't go back and modify earlier objects
- Strictly linear workflow
- Can't build complex assemblies with references between parts

### 6. Single-threaded Fusion HTTP Server

The HTTP server uses `HTTPServer.serve_forever()` in a daemon thread:
- Can only handle one request at a time
- Concurrent requests will queue

**Impact:** Low (Claude makes sequential tool calls), but limits scalability.

### 7. No Visual Feedback in Claude

When tools execute:
- Claude sees text responses ("Rectangle created")
- User must switch to Fusion to see actual geometry
- No screenshots or visual confirmation

**Impact:** User experience could be better with visual feedback.

### 8. Limited Geometry Types

Current sketch primitives:
- Rectangles (extrudable)
- Circles (extrudable)
- Lines (NOT extrudable when separate)

**Missing:**
- Polygons, arcs, splines
- Polylines/connected line segments
- Complex custom shapes

### 9. Validation Edge Cases

Some validation could be improved:
- Chamfer distance validation depends on geometry (can fail at runtime)
- No validation that fillet radius fits the geometry
- Rectangle dimensions not validated against each other

### 10. Local Execution Only

Fusion 360 scripts must run locally on the machine with Fusion installed:
- Cannot deploy to cloud
- User must have Fusion 360 running
- Limits accessibility and scalability

## Potential Improvements

### High Priority (Most Impactful)

#### 1. Polyline/Multi-Point Sketch Tool
**Problem:** Each sketch_line creates a separate sketch, making it impossible to create extrudable custom shapes.

**Solution:**
```python
# New tool: sketch_polyline
{
    "points": [
        {"x": 0, "y": 0, "z": 0},
        {"x": 5, "y": 0, "z": 0},
        {"x": 5, "y": 5, "z": 0},
        {"x": 0, "y": 5, "z": 0}
    ],
    "closed": true  # Connect last point to first
}
```

**Implementation:**
```python
# In fusion_http_server.py:
sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)
lines = sketch.sketchCurves.sketchLines

# Loop through points array - works with ANY number of points
for i in range(len(points) - 1):
    p1 = adsk.core.Point3D.create(points[i]["x"], points[i]["y"], points[i]["z"])
    p2 = adsk.core.Point3D.create(points[i+1]["x"], points[i+1]["y"], points[i+1]["z"])
    lines.addByTwoPoints(p1, p2)

# If closed, connect last to first
if closed:
    p_last = adsk.core.Point3D.create(points[-1]["x"], points[-1]["y"], points[-1]["z"])
    p_first = adsk.core.Point3D.create(points[0]["x"], points[0]["y"], points[0]["z"])
    lines.addByTwoPoints(p_last, p_first)
```

**Why it's critical:**
- Solves the biggest current limitation (can't extrude custom shapes)
- Enables creating ANY polygon: triangles, pentagons, L-shapes, complex brackets
- All lines in ONE sketch = valid extrudable profile
- Standard CAD feature that users expect
- Works with variable number of points using array/list structure

**LLM Considerations:**
- Claude can easily understand "draw a triangle with these 3 points"
- Array structure handles any number of points dynamically
- No need for Claude to track point count ahead of time
- Very intuitive for Claude to generate point coordinates

**Implementation approach:**
- Use JSON array for points (arbitrary length)
- Loop through array in Fusion script
- `len(points)` determines how many iterations
- Same code works for 3 points or 100 points

#### 2. Explicit Plane Selection
**Problem:** All sketches are hardcoded to XZ plane, limiting design flexibility.

**Solution:**
```python
# Add "plane" parameter to all sketch tools
{
    "plane": "XY",  # or "XZ" (default), "YZ"
    "length": 10,
    "width": 5
}

# In fusion_http_server.py:
plane = request_data["params"].get("plane", "XZ")
if plane == "XY":
    sketch = rootComp.sketches.add(rootComp.xYConstructionPlane)
elif plane == "XZ":
    sketch = rootComp.sketches.add(rootComp.xZConstructionPlane)
elif plane == "YZ":
    sketch = rootComp.sketches.add(rootComp.yZConstructionPlane)
```

**Why it's important:**
- Explicit control over sketch orientation
- Clearer intent than coordinate-based plane inference
- Enables perpendicular features easily
- Matches how users think about CAD ("sketch on front plane")

**LLM Considerations:**
- Very clear for Claude: "sketch rectangle on XY plane"
- No ambiguity about which plane is intended
- Easy to document and understand

**Could be implemented as:**
- Parameter in each sketch tool
- OR separate tool to set construction plane for subsequent operations

### Medium Priority (Useful but More Complex)

#### 3. Named Sketch References for Extrusion
**Problem:** Can only extrude the most recent sketch.

**Solution:**
```python
# Option A: Sketch indices
{
    "distance": 10,
    "sketch_index": 2  # Extrude the 3rd sketch (0-indexed)
}

# Option B: Named sketches (better!)
{
    "distance": 10,
    "sketch_name": "mounting_plate"
}

# In fusion_http_server.py:
# When creating sketch:
sketch.name = request_data["params"].get("name", f"sketch_{sketches.count}")

# When extruding:
sketch_name = request_data["params"].get("sketch_name")
for s in rootComp.sketches:
    if s.name == sketch_name:
        sketch = s
        break
```

**Why it's useful:**
- Non-linear workflow (go back and modify earlier sketches)
- Complex designs with multiple sketches
- Fix mistakes without starting over

**LLM Considerations:**
- Claude needs to remember which sketch is which
- Works well with descriptive names: "base_plate", "mounting_hole"
- Requires Claude to track state across multiple tool calls
- More cognitive load for the LLM

**Tradeoffs:**
- More cognitive load for Claude (must remember names)
- More parameters to manage
- Could confuse Claude if not documented well
- Requires keeping track of sketch names throughout conversation

#### 4. Selective Edge Fillet/Chamfer
**Problem:** All edges get same treatment, no selective control.

**Solution:**
```python
# Option A: Edge indices (fragile - edges renumber)
{
    "radius": 0.5,
    "edge_indices": [0, 2, 5]
}

# Option B: Geometric criteria (better!)
{
    "radius": 0.5,
    "filter": "vertical"  # or "top", "bottom", "horizontal"
}

{
    "radius": 0.5,
    "min_length": 5  # Only edges longer than 5cm
}
```

**Why it's useful:**
- Professional results (selective filleting is standard CAD practice)
- Design flexibility (sharp edges in some places, rounded in others)
- More realistic CAD workflow

**LLM Considerations:**
- Hard for Claude to know which edge is which without visual feedback
- Edge indices change when geometry is modified
- Geometric criteria easier for Claude to understand ("fillet the top edges")
- Without visual feedback, Claude can't "see" which edges exist

**Tradeoffs:**
- Edge tracking is complex
- Requires sophisticated edge selection logic
- Without visual feedback, Claude can't verify which edges are selected
- Edge numbering can change with geometry modifications

#### 5. Profile Selection for Extrusion
**Problem:** Always extrudes first profile, can't choose from multi-profile sketches.

**Solution:**
```python
# Option A: Profile index
{
    "distance": 10,
    "profile_index": 1  # Extrude the 2nd profile
}

# Option B: Profile names (requires tracking)
{
    "distance": 10,
    "profile_name": "inner_hole"
}
```

**Why it's useful:**
- One sketch can define multiple features
- Efficient workflow (don't need separate sketches)
- Standard CAD practice

**LLM Considerations:**
- Hard to identify which profile is which
- Profiles don't have names by default in Fusion API
- Would need metadata or index tracking
- Hard for LLM to keep track of which profile is which unless named well

**Tradeoffs:**
- Complex to implement profile naming
- Claude can't "see" which profile is which
- Less intuitive than one-sketch-per-feature
- Requires additional metadata tracking

### Low Priority (Nice to Have)

6. **More sketch primitives:** Arcs, ellipses, splines, polygons
7. **Boolean operations:** Union, subtract, intersect multiple bodies
8. **Measurement tools:** Get dimensions, volume, mass
9. **Pattern tools:** Linear, circular, rectangular patterns
10. **Visualization:** Screenshots after each operation
11. **Transaction/undo support:** Rollback on errors
12. **Configuration:** Adjustable timeouts, ports, validation ranges
13. **Cloud deployment:** Making it run on the cloud (major architectural change)

## What I'd Do Next With More Time

### Immediate Next Steps (Next 2-3 hours)

1. **Implement polyline tool**
   - Solves the biggest current limitation
   - Enables creating any polygon shape
   - Relatively straightforward to implement
   - High impact for usability

2. **Add explicit plane selection**
   - Simple parameter addition
   - Huge improvement in clarity
   - Enables perpendicular features

### Short Term (Next week)

3. **Better error messages**
   - Include more diagnostic information
   - Suggest fixes for common mistakes
   - Add examples of correct usage

4. **Named sketch references**
   - Allow non-linear workflows
   - Enable more complex designs
   - Requires state tracking

5. **More operation types**
   - Revolve (for cylindrical parts)
   - Loft/sweep
   - Shell (hollow out solids)

### Medium Term (Next month)

6. **Selective edge operations**
   - Implement geometric edge filtering
   - Better than index-based selection
   - More robust to geometry changes

7. **Visual feedback**
   - Take screenshots after operations
   - Return images to Claude
   - Embed in tool responses

8. **Object ID system**
   - Track sketches, bodies, features with IDs
   - Enable references between operations
   - Support non-linear workflows

### Long Term (Future)

9. **Assembly support**
   - Multiple components
   - Constraints and joints
   - Component references

10. **Parametric design**
    - Named dimensions
    - Drive dimensions programmatically
    - Design tables

11. **Advanced validation**
    - Geometry-aware validation (check fillet radius fits)
    - Interference detection
    - Design rule checking

12. **Cloud deployment**
    - Major architectural change
    - Would require Fusion API cloud access or different approach
    - Currently limited by local execution requirement

## Design Philosophy

**Keep it minimal:**
- Focus on core functionality
- Only essential features
- Clear, focused tools

**Make it debuggable:**
- Each component testable in isolation
- Clear error messages at each layer
- Structured, predictable responses

**Document everything:**
- Explain why, not just what
- Acknowledge limitations openly
- Provide troubleshooting steps

**Production-ready structure:**
- Clean separation of concerns
- Extensible design
- Scalable architecture (even if current scope is limited)

**Optimize for LLM understanding:**
- Clear, unambiguous tool descriptions
- Explicit parameter documentation
- Warn about limitations in descriptions
- Use examples in documentation

**Iterative development:**
- Start with simplest tools and test thoroughly
- Build confidence before adding complexity
- Easier to debug and iterate

## Time Investment

**Initial Implementation:**
- Understanding MCP protocol and SDK: 1 hour
- Setting up Fusion HTTP server: 2 hours
- Implementing MCP server: 1.5 hours
- Testing end-to-end: 1 hour
- Initial documentation: 1.5 hours

**Enhancements:**
- Adding circle and line tools: 1 hour
- Implementing 3D positioning: 2 hours
- Adding chamfer and clear tools: 1 hour
- Improving error messages: 1 hour
- Coordinate system documentation: 1 hour
- Refining tool descriptions for Claude: 2 hours

**Total: ~15 hours**

## Lessons Learned

1. **Async/await complexity:** Understanding when to use `await` vs synchronous operations was initially confusing. Key insight: only I/O operations need `await`, not data processing.

2. **MCP tool schemas:** The `inputSchema` structure is critical for Claude to understand tools. Clear descriptions with axis information help Claude make correct tool calls.

3. **Fusion API quirks:** Point3D order and construction plane behavior took experimentation to understand. Documentation was sparse for some edge cases.

4. **Error handling layers:** Three layers of error handling (validation → HTTP → Fusion) catches errors at the right level and provides better user feedback.

5. **LLM limitations:** Without visual feedback, Claude struggles with spatial reasoning. Explicit axis documentation (X=left-right, Y=up-down, Z=forward-back) helps significantly.

6. **Stateful operations:** "Most recent" pattern works well for linear workflows but limits complex designs. Would need object tracking for production.

7. **Array/list structures:** Using arrays for variable-length data (like polyline points) is more flexible than fixed parameters and works naturally with JSON.

8. **Tool description verbosity:** Verbose tool descriptions (including axis info, plane explanations, limitations) actually help Claude make better decisions, even if they seem long.

9. **Iterative development value:** Starting with simplest tools and testing thoroughly before adding complexity made debugging much easier and faster.

10. **Try/except utility:** Exception handling with try/except blocks provides much better error messages and user experience than letting errors crash the server.
