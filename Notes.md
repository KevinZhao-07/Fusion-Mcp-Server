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

I considered embedding the MCP server inside Fusion, but:
- Fusion's Python environment is restrictive
- Installing MCP SDK dependencies in Fusion is difficult
- stdio communication from within Fusion is problematic

### Tool Design

**Three minimal tools:** `create_rectangle_sketch`, `extrude_profile`, `fillet_edges`

These were chosen to demonstrate the complete workflow: 2D sketch → 3D body → finishing operation.

**Why rectangles only?**
- Simplest closed profile that can be extruded
- No complex constraints or dimensions needed
- Easy to validate (just two parameters)
- Good for demonstrating the concept

**Validation ranges:**
- Length/width: 0 < x < 1000 cm (prevents absurdly large/small values)
- Extrude distance: 0 < x < 1000 cm (same reasoning)
- Fillet radius: 0 < x < 10 cm (prevents fillets larger than typical geometry)

These limits are arbitrary but reasonable for a demo. Production would need better validation.

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

### Error Handling

**Three layers of error handling:**

1. **MCP Server validation** (server.py)
   - Checks parameter types and ranges
   - Returns friendly error messages
   - Happens before HTTP call (faster feedback)

2. **HTTP errors** (connection, timeout)
   - Caught by `httpx` exception handlers
   - Returns helpful diagnostic messages
   - Tells users how to fix common issues

3. **Fusion API errors** (fusion_http_server.py)
   - Wrapped in try/except
   - Returns 500 status with error details
   - Example: "No profile found in sketch"

**Why three layers?**
- Catches different types of failures
- Each layer has different information available
- Provides actionable error messages at each level

### Communication Format

**HTTP POST with JSON:**
```json
{
  "tool": "sketchRectangle",
  "params": {"length": 10, "width": 10}
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
- Rejected: Adds complexity, cm is fine for a demo

## Known Limitations

### 1. Single-threaded Fusion HTTP Server

The HTTP server uses `HTTPServer.serve_forever()` in a daemon thread. This means:
- Can only handle one request at a time
- Concurrent requests will queue
- Not a problem for Claude (sequential calls) but limits scalability

**Impact:** Low (Claude makes sequential tool calls)

### 2. No Transaction Support

If a sequence of operations fails midway:
- Previous operations are NOT rolled back
- User is left with partial geometry
- Have to manually undo or delete

**Example:**
```
1. create_rectangle_sketch(10, 10) ✅
2. extrude_profile(5) ✅
3. fillet_edges(100) ❌ (radius too large)
```
Result: Box without fillets (not automatically cleaned up)

**Better approach:** Implement undo/redo or atomic operations

### 3. Assumes Fresh Design

The tools assume they're working in a clean design:
- Rectangle created at origin (0,0,0)
- No collision detection
- Doesn't check for existing geometry

**Impact:** Works fine for demos, breaks in complex designs

### 4. Limited Geometry Types

Only supports rectangles. Can't create:
- Circles, polygons, splines
- Arbitrary sketches
- Multiple disconnected bodies
- Assemblies

**Reason:** Kept minimal for the demo (3-5 tools limit)

### 5. No Visual Feedback in Claude

When tools execute:
- Claude sees text responses ("✅ Rectangle created")
- User must switch to Fusion to see the actual geometry
- No screenshots or visual confirmation

**Impact:** User experience could be better

### 6. Hardcoded Plane and Position

- Rectangle always on XZ plane
- Always starts at origin (0,0,0)
- Can't specify position or orientation

**Better design:** Add parameters for plane selection and position

### 7. Fillet All Edges

The fillet tool rounds ALL edges with the same radius:
```python
for edge in body.edges:
    edges.add(edge)
```

Can't:
- Select specific edges
- Use different radii for different edges
- Choose which edges to fillet

**Impact:** Works for simple boxes, limiting for complex shapes

## What I'd Do Next With More Time

### High Priority

1. **Add more sketch primitives**
   - Circle (center point + radius)
   - Polygon (center + sides + radius)
   - Line tool for custom shapes

2. **Better error messages**
   - Include Fusion log output in responses
   - Add screenshots on error
   - Suggest fixes for common mistakes

3. **Object selection**
   - Return unique IDs from operations
   - Let tools reference specific objects
   - Example: `extrude(sketch_id="sketch1", distance=5)`

4. **More operations**
   - Revolve (for cylindrical shapes)
   - Loft/sweep
   - Boolean operations (union, subtract, intersect)
   - Chamfer (in addition to fillet)

5. **Better state management**
   - Track active design/component
   - Support multiple bodies
   - Named references for geometry

### Medium Priority

6. **Plane and position control**
   ```python
   create_rectangle_sketch(
       length=10,
       width=10,
       plane="XY",  # or "XZ", "YZ"
       origin=[10, 0, 5]  # offset from global origin
   )
   ```

7. **Selective fillet/chamfer**
   - Select edges by index or type
   - Different radii per edge set

8. **Transaction support**
   - Wrap operations in begin/commit blocks
   - Rollback on error
   - Or: return undo tokens that can be used later

9. **Measurement/query tools**
   - Get bounding box
   - Calculate volume/mass
   - List all bodies in design
   - Export to different formats

10. **Visualization**
    - Take screenshot after each operation
    - Return image to Claude
    - Embed in tool response

### Low Priority

11. **Configuration**
    - Make port configurable
    - Support multiple Fusion instances
    - Custom timeout values

12. **Logging**
    - Better structured logging
    - Save operation history
    - Export command log

13. **Testing**
    - Unit tests for MCP server
    - Integration tests with mock HTTP server
    - Fusion script tests (harder, limited testing framework)

14. **Performance**
    - Connection pooling
    - Async operations in Fusion (if possible)
    - Batch multiple operations

15. **Security**
    - Add authentication token
    - Restrict to localhost only (already done)
    - Rate limiting

## Time Breakdown

- Understanding MCP protocol and SDK: 1 hour
- Setting up Fusion HTTP server: 2 hours
  - Learning Fusion API
  - Testing sketch/extrude/fillet operations
  - Debugging threading issues
- Implementing MCP server: 1.5 hours
  - Writing tool definitions
  - Implementing async HTTP calls
  - Error handling
- Testing end-to-end: 1 hour
  - Setting up Claude Desktop config
  - Debugging connection issues
  - Testing the full workflow
- Documentation: 1.5 hours
  - README with setup instructions
  - This notes file
  - Code comments
- Buffer/polish: 1 hour

**Total: ~8 hours**

## Design Philosophy

**Keep it minimal:**
- 3 tools (not 12 half-baked ones)
- Only essential features
- Clear, focused functionality

**Make it debuggable:**
- Each component testable in isolation
- Clear error messages
- Structured responses

**Document everything:**
- Explain why, not just what
- Acknowledge limitations
- Provide troubleshooting steps

**Production-ready structure:**
- Even though this is a demo, the architecture could scale
- Clean separation of concerns
- Extensible design
