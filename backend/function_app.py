import azure.functions as func

from custom_gpt_tools import main as custom_gpt_tools_main

app = func.FunctionApp()


@app.function_name(name="custom_gpt_tools")
@app.route(route="custom_gpt_tools", methods=["GET"], auth_level=func.AuthLevel.FUNCTION)
def custom_gpt_tools(req: func.HttpRequest) -> func.HttpResponse:
    return custom_gpt_tools_main(req)
