Design Decisions:





Improvements:
Specific plane selection (very useful)
    -A tool that the llm can use
    -In the fusion script sets the construction plane
Able to choose determine edges in order to fillet and chamfer
    -Need to keep track of edges
    -Hard for the llm to know which edge is which
Being able to make extrusions on a selected past sketch
    -Would require you to keep track of profiles or you could keep track of sketch index
    -Hard for the llm to know which profile is which unless is named well
Able to extrude a certain profile
    -Keep track of each profile and make sure it's closed
    -Hard to be identity what to do by the llm
Creating a polyline(very useful)
    -Makes it so you can create essentially any none curved object/shape
Making it run on the cloud
