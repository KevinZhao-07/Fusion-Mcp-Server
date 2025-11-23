# Design Decisions and Notes

## CAD Software
**Choice:** Fusion 360

**Why:** Personal familiarity, runs locally

**Tradeoff:** Fusion caches Python scripts, so code changes would only take place once Fusion is closed and reopened. Significantly slowed down iteration.

## Language Choice
**Choice:** Python

**Why:** Fusion's default language and personal familiarity

## Server Architecture

### Two-Server Architecture
I implemented a two-server design:
- **Fusion HTTP Server** - Runs inside Fusion 360, has direct access to the Fusion API
- **MCP Server** - Runs as standalone Python script, communicates with Claude Desktop via MCP protocol

### Why Two Servers Instead of One?

**1. Separation of Tasks**
- MCP Server handles: protocol communication, tool definition, and most parameter validation
- Fusion Server handles: CAD operations, API calls

**2. Independent Testing**
- I could test the Fusion server using curl commands without involving MCP
- Once curl tests passed, I knew the Fusion API calls worked
- Then I built the MCP layer knowing the Fusion API calls worked, also clearer requirements once Fusion worked
- If something broke, I knew which layer caused it

**3. Different Runtime Environments**
- MCP requires async/await and stdio communication
- Fusion add-ins have their own run/stop functions and threading requirements
- Mixing these in one codebase would create complexity and potential conflicts

**4. Swappability**
- If I wanted to swap Fusion for another CAD program (Onshape) I only rewrite the Fusion server
- The MCP server stays the same

### Tradeoffs
- Two codebases to maintain
- HTTP overhead
- More initial setup complexity
- The integration of both layers and having extra network layer adds potential failure points

### Development Approach

**Built Bottom Up:**
1. Fusion HTTP server
2. Tested with curl to verify API calls worked
3. MCP server
4. Integrate and test end to end

**Why this order:**
- De-risked the hard part (Fusion API) first
- Each layer could be tested independently
- When integration issues arose, I knew which layer to debug

## Tool Implementation

### Design Philosophy
The assignment emphasized "3-5 tools over 12 half-baked ones." I prioritized tools that create a complete logical CAD workflow.

I developed bottom-up, starting with the simplest tools to learn the Fusion API, then building towards more complex operations while following a logical CAD workflow. I also batched similar tools together since they share similar logic.

### Phase 1: Core Workflow
My first goal was to complete one logical CAD workflow: sketch → extrude → finish edges

- **sketchLine** - Basic line sketch. Simplest sketch type, used to familiarize myself with how the Fusion API handles points and planes.
- **sketchRectangle** - Rectangular profile. Built on sketchLine knowledge. Initially thought to draw 4 individual lines, but discovered Fusion has a built-in addTwoPointRectangle function - learned to check API docs before implementing manually.
- **extrude** - Turn 2D sketch into 3D body. Natural next step after sketching.
- **fillet** - Round all edges. First finishing operation for completed 3D bodies.
- **chamfer** - Bevel all edges. Same pattern as fillet, easy to add once fillet worked.
- **clear** - Remove all bodies from design. Realized I needed this for faster testing. Should have implemented earlier, essential for iteration but also functionality.

**Result:** Complete workflow from 2D sketch to finished 3D object with edge treatments.

### Phase 2: Expanding for Adam Logo
Once the core workflow was solid, I set a new goal: create the Adam company logo

This required new capabilities, so I followed the same process:
- **sketchCircle** - Circular profile. Logo requires circles, not just rectangles.
- **extrudeCut** - Remove material using sketch profile. Logo needs cutouts, not just adding material. Same design pattern as extrude.

Same development approach: batch similar tools, build on existing patterns, test incrementally.

### Key Design Decisions

#### Extrusion on Last Sketch
For extrude, extrudeCut, fillet, and chamfer, I chose to operate on the most recent sketch/body rather than requiring object selection.

**Why this approach:**
- No need to track or label every sketch/body
- Simpler API for the LLM to follow
- Matches natural workflow: create sketch → immediately extrude it

**Tradeoff:**
- Less control - can't extrude older sketches
- Can't select specific profiles or edges
- Limits complex multi-body workflows

#### Fillets and Chamfers on All Edges

**Why this approach:**
- Tracking individual edges is complex - each body can have 12+ edges, each needing a unique identifier
- Even if implemented, edge selection would be difficult for an LLM to follow without visual feedback
- The LLM can't "see" the model, so instructions like "fillet the top-left edge" become ambiguous
- Applying to all edges covers the most common use case: creating a uniformly finished object
- Keeps the API simple and predictable

**Tradeoff:**
- Cannot fillet/chamfer specific edges only
- Cannot apply different radii to different edges
- Less flexibility for complex designs where only certain edges should be rounded
- A real CAD workflow often requires selective edge treatment

### Tool Count Justification
Although I implemented 8 tools, they group into 3 unique categories:
- **Sketch tools** (line, rectangle, circle) - same pattern, different shapes
- **Extrude tools** (extrude, extrudeCut) - same pattern, different operations
- **Edge tools** (fillet, chamfer) - same pattern, different edge treatments
- Plus one utility tool (clear)

Each new tool built on knowledge from the previous one, making development more efficient.

## Single Plane
I kept all the sketches to the XZ plane rather than allowing plane selection.

**Why this approach:**
- Ensure simplicity and consistent behavior
- Allowed me to verify all logic was correct before adding complexity (allowed non-origin sketches)
- Chose XZ specifically because of familiarity from personal experience and coursework
- Reduce variables when debugging

**Tradeoff:**
- Cannot create sketches on XY or YZ plane
- Real CAD workflows require sketching on different planes

## Validation Strategy
I aimed for validations that are as "free" as possible, which means maximizing the range of the arguments.

### Two Types of Validation

**Absolute Validation (handled in MCP server):**
- Arguments that have defined bounds and don't need to know the current model state
- Example: radius must be greater than 0
- Fast feedback - catches errors before HTTP request is made

**Proportional Validation (handled in Fusion server):**
- Arguments that depend on the current geometry
- Example: chamfer and fillets
- Requires access to the actual model's dimensions

### Why Proportional Validation Matters
Consider a fixed validation like 0 < chamferDistance < 10. If you have a 2x2x2 cube, any chamfer greater than 1 will fail in Fusion, but this validation wouldn't catch this. But proportional validation scales with the geometry, allowing the maximum valid range for any given shape and is more accurate to an actual CAD workflow.

### Why Split Between Servers
The MCP server doesn't track body dimensions so it is unable to validate it.

**Tradeoff:** Since proportional validation requires the Fusion server to handle it, you need to wait for the HTTP round-trip, making it slower.

## Three-Layer Error Handling

**MCP Server Validation**
- Checks parameter type and range
- Before HTTP call - faster feedback
- Feedback to user

**HTTP Errors**
- Caught by `httpx` exception handlers
- Handles network issues
- Tells users how to fix common issues
- 10-second timeout prevents indefinite waiting

**Fusion API Errors**
- Wrapped in try and except
- Returns 500 with error details

**Why three layers:** By having 3 layers to address and handle errors and using try and except I can localize and pinpoint issues in the code.

## Async and Threading

**Why Async in MCP Server:**
- MCP protocol requires async functions
- Prevents blocking while waiting for HTTP responses from Fusion
- Allows the server to remain responsive during network calls

**Why Threading in Fusion Server:**
- HTTP server must run continuously to receive requests
- Fusion's run() function must return quickly to keep UI responsive
- Background thread allows both to happen simultaneously
- Daemon thread ensures clean shutdown when Fusion closes

## Design Decision: HTTP Server Choice (http.server vs Flask/FastAPI)

I chose Python's built-in `http.server` module instead of web frameworks like Flask or FastAPI.

**Why http.server:**
- Zero dependencies - part of Python's standard library, no installation needed
- Sufficient for simple use case (Few endpoints, localhost only, single client)
- Easy integration with threading model required for Fusion add-ins
- Aligns with assignment emphasis on "minimal" implementation

**What Flask/FastAPI would provide:**
- Cleaner routing syntax with decorators
- Automatic JSON parsing and response creation
- Built-in request validation

**Why those features aren't needed:**
- Only 8 simple endpoints to route
- Manual JSON handling is straightforward for this scale
- Localhost-only communication
- Single client (just the MCP server)

**Threading consideration:**
Flask's `app.run()` blocks forever, which conflicts with Fusion's requirement that the `run()` function returns quickly. While Flask can run in a thread, it adds complexity without benefit for this use case.

**Tradeoff:**
- More manual code (reading requests, parsing JSON, routing with if/elif)
- Less elegant than Flask's decorator syntax
- But: simpler dependencies, easier threading, appropriate for scope

## Limitations/Known Issues

**No Plane Selection**
- All sketches restricted to XZ plane
- Could be a tool
- Would require revamping sketch logic to handle different construction planes

**No Edge Selection**
- Fillet and chamfer apply to all edges
- Selective edge operations would require tracking and labeling each edge
- Since LLM cannot "see" the model, it would be hard to keep track and identify

**No Profile Selection**
- Extrude operations only work on the most recent sketch's profile
- Unable to select certain profiles
- Would require you to keep track of profiles or you could keep track of sketch index
- LLM can't see which profile is which

**No Polyline Tool**
- Right now limited to rectangles and circles
- Creating polyline would allow creation of any non-curved object/shape

**Local Only**
- Server runs on localhost
- No cloud-based deployment

## What I'd Do With More Time

**Priority 1: Polyline Tool**
- Opens the most doors for complex geometry
- Less challenging than edge/profile selection
- Would allow creating arbitrary polygonal shapes

**Priority 2: Plane Selection**
- Add ability to sketch on XY, YZ, or custom planes
- Enables true 3D modeling workflows

**Priority 3: Smarter Edge Selection**
- Not fully specific (too complex for LLM), but categorical
- Options like "top edges", "bottom edges", "vertical edges"

**Priority 4: Onshape Implementation**
- Adam uses Onshape, so this would be directly relevant
- Would also explore cloud-based approach rather than local server