from pathlib import Path


def get_template_html():
    """
    Load and return the HTML template from the static files.
    
    Returns:
        str: HTML content of the index.html file
    """
    template_path = Path(__file__).parent / 'index.html'
    
    try:
        with open(template_path, 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Template file not found at {template_path}. "
            "Ensure the 'static' directory contains index.html"
        )


def render_template():
    """
    Main function to render the template.
    This can be used by Flask/FastAPI to serve the HTML.
    
    Returns:
        str: Complete HTML page with linked CSS and JS
    """
    return get_template_html()


# For Flask integration
def flask_render():
    """
    Flask-specific render function.
    Usage in Flask:
        from template_ui import flask_render
        
        @app.route('/')
        def index():
            return flask_render()
    """
    from flask import render_template
    return render_template('index.html')


# For FastAPI integration
def fastapi_render():
    """
    FastAPI-specific render function.
    Usage in FastAPI:
        from fastapi.responses import HTMLResponse
        from template_ui import fastapi_render
        
        @app.get("/", response_class=HTMLResponse)
        async def index():
            return fastapi_render()
    """
    return get_template_html()