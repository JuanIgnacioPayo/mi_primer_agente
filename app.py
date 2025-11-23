from flask import Flask, render_template, request, jsonify
from agente import get_agent_response
from langchain_core.messages import AIMessage, HumanMessage

app = Flask(__name__)

# MODIFICACIÓN: Lista para almacenar el historial de la conversación.
# En una aplicación real, esto estaría en una base de datos o sesión de usuario.
chat_history = []

@app.route('/')
def index():
    return render_template('index.html')

import json

@app.route('/chat', methods=['POST'])
def chat():
    global chat_history
    user_message = request.json.get('message')
    
    # El historial se pasa al agente para que tenga contexto
    agent_response = get_agent_response(user_message, chat_history)
    
    # Actualizamos el historial con el nuevo turno de la conversación
    # Guardamos la respuesta cruda (con prefijo si lo tiene) para mantener la consistencia
    chat_history.append(HumanMessage(content=user_message))
    chat_history.append(AIMessage(content=agent_response))
    
    # Verificamos si la respuesta es un análisis político en JSON
    if agent_response.startswith("ANALYSIS_JSON::"):
        try:
            # Quitamos el prefijo y parseamos el JSON
            json_string = agent_response.replace("ANALYSIS_JSON::", "", 1)
            analysis_data = json.loads(json_string)
            # Enviamos una respuesta con un tipo específico para que el frontend la maneje
            return jsonify({'type': 'analysis', 'data': analysis_data})
        except (json.JSONDecodeError, TypeError) as e:
            # Si hay un error, enviamos una respuesta de texto plano con el error
            error_message = f"Error al procesar el análisis: {e}"
            return jsonify({'type': 'text', 'response': error_message})
    else:
        # Si es una respuesta normal, la enviamos como texto plano
        return jsonify({'type': 'text', 'response': agent_response})

# Ruta para reiniciar la conversación
@app.route('/reset', methods=['POST'])
def reset():
    global chat_history
    chat_history = []
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(debug=True)
