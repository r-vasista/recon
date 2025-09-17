def success_response(data, message = None):
    return {"status": True, "data":data, "message":message}

def error_response(message):
    return {"status": False, "message":message}