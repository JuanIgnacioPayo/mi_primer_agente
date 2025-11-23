document.addEventListener('DOMContentLoaded', () => {
    const chatForm = document.getElementById('chat-form');
    const userInput = document.getElementById('user-input');
    const chatBox = document.getElementById('chat-box');
    const resetButton = document.getElementById('reset-button');
    const fullscreenButton = document.getElementById('fullscreen-button');

    chatForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const message = userInput.value.trim();
        if (message === '') return;

        appendMessage(message, 'user-message');
        userInput.value = '';

        const loadingIndicator = showLoadingIndicator();

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ message: message }),
            });

            const data = await response.json();

            // Diferenciamos el tipo de respuesta
            if (data.type === 'analysis') {
                appendAnalysisCard(data.data);
            } else {
                appendMessage(data.response, 'agent-message');
            }

        } catch (error) {
            console.error('Error al comunicarse con el agente:', error);
            appendMessage('Lo siento, hubo un error al procesar tu mensaje.', 'agent-message');
        } finally {
            loadingIndicator.remove();
        }
    });

    resetButton.addEventListener('click', async () => {
        try {
            await fetch('/reset', { method: 'POST' });
            chatBox.innerHTML = ''; // Limpia la caja de chat
            appendMessage('Hola, ¿en qué puedo ayudarte?', 'agent-message'); // Añade el mensaje de bienvenida
        } catch (error) {
            console.error('Error al reiniciar el chat:', error);
        }
    });

    fullscreenButton.addEventListener('click', () => {
        document.body.classList.toggle('chat-fullscreen');
        if (document.body.classList.contains('chat-fullscreen')) {
            fullscreenButton.textContent = 'Vista Normal';
        } else {
            fullscreenButton.textContent = 'Pantalla Completa';
        }
    });

    function appendMessage(message, className) {
        const messageElement = document.createElement('div');
        messageElement.classList.add('message', className);
        // Usamos innerHTML para poder renderizar Markdown simple o puntos de carga.
        // Para una implementación más segura y completa, se podría usar una librería como `marked.js`
        messageElement.innerHTML = message.replace(/\n/g, '<br>');
        chatBox.appendChild(messageElement);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    // NUEVA FUNCIÓN para renderizar la tarjeta de análisis
    function appendAnalysisCard(data) {
        const card = document.createElement('div');
        card.classList.add('message', 'agent-message', 'analysis-card');

        // Función auxiliar para crear secciones de la tarjeta
        const createSection = (title, content, className = '') => {
            if (!content || (Array.isArray(content) && content.length === 0) || (typeof content === 'string' && content.trim() === '')) {
                return '';
            }
            let contentHtml = '';
            if (Array.isArray(content)) {
                contentHtml = `<ul>${content.map(item => `<li>${item}</li>`).join('')}</ul>`;
            } else {
                contentHtml = `<p>${content}</p>`;
            }
            return `
                <div class="card-section ${className}">
                    <h4>${title}</h4>
                    ${contentHtml}
                </div>
            `;
        };

        let mediaPerspectivesHtml = '';
        if (data.media_perspectives && data.media_perspectives.length > 0) {
            mediaPerspectivesHtml = data.media_perspectives.map(p => `
                <div class="media-perspective-item">
                    <h5><a href="${p.url}" target="_blank" rel="noopener noreferrer">${p.title}</a> (${p.media_outlet})</h5>
                    ${createSection('Resumen', p.summary_text)}
                    ${createSection('Hechos Clave', p.key_facts)}
                    ${createSection('Ángulo del Medio', p.media_angle)}
                </div>
            `).join('');
        }

        card.innerHTML = `
            <div class="card-header">
                <h3>Análisis Político: ${data.topic}</h3>
            </div>
            <div class="card-body">
                ${createSection('Hechos Comunes', data.common_facts)}
                
                <div class="card-section">
                    <h4>Perspectivas por Medio</h4>
                    <div class="media-perspectives-container">
                        ${mediaPerspectivesHtml}
                    </div>
                </div>

                ${createSection('Discrepancias / Puntos a Destacar', data.discrepancies, 'discrepancies-section')}
            </div>
        `;

        chatBox.appendChild(card);
        chatBox.scrollTop = chatBox.scrollHeight;
    }

    function showLoadingIndicator() {
        const loadingElement = document.createElement('div');
        loadingElement.id = 'loading-indicator';
        loadingElement.classList.add('message', 'agent-message');
        loadingElement.innerHTML = `
            <span>Elaborando una respuesta</span>
            <span class="dot">.</span>
            <span class="dot">.</span>
            <span class="dot">.</span>
        `;
        chatBox.appendChild(loadingElement);
        chatBox.scrollTop = chatBox.scrollHeight;
        return loadingElement;
    }
});
