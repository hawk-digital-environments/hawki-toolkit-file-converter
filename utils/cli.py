import uvicorn


def dev():
    uvicorn.run("main:app", reload=True, host="0.0.0.0", port=8001)
