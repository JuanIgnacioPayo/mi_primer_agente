import os
import json
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_classic import hub
from langchain_classic.agents import create_react_agent, AgentExecutor
from langchain_core.tools import Tool
from langchain_core.messages import AIMessage, HumanMessage
from ddgs import DDGS
import requests
from bs4 import BeautifulSoup

# 1. CONFIGURACIÓN
# En un entorno real, usa variables de entorno (.env).
# Pega aquí tu API Key de Google:
os.environ["GOOGLE_API_KEY"] = "AIzaSyAgnFaJ0PBwOsfHJgNs-qQLonmvbfiu7jE" # <--- REEMPLAZA ESTE VALOR CON TU CLAVE DE API REAL

SOURCES_CONFIG = [
    # Medios Nacionales
    {
        "name": "Clarín",
        "domain": "clarin.com",
        "type": "national_news",
        "political_leaning": "Centro-derecha",
        "extraction_method": "scrape_html",
        "base_url": "https://www.clarin.com/"
    },
    {
        "name": "La Nación",
        "domain": "lanacion.com.ar",
        "type": "national_news",
        "political_leaning": "Centro-derecha",
        "extraction_method": "scrape_html",
        "base_url": "https://www.lanacion.com.ar/"
    },
    {
        "name": "Página/12",
        "domain": "pagina12.com.ar",
        "type": "national_news",
        "political_leaning": "Izquierda",
        "extraction_method": "scrape_html",
        "base_url": "https://www.pagina12.com.ar/"
    },
    {
        "name": "Infobae",
        "domain": "infobae.com",
        "type": "national_news",
        "political_leaning": "Centro-derecha",
        "extraction_method": "scrape_html",
        "base_url": "https://www.infobae.com/"
    },
    {
        "name": "Perfil",
        "domain": "perfil.com",
        "type": "national_news",
        "political_leaning": "Centro-izquierda",
        "extraction_method": "scrape_html",
        "base_url": "https://www.perfil.com/"
    },
    {
        "name": "Ámbito Financiero",
        "domain": "ambito.com",
        "type": "national_news",
        "political_leaning": "Centro",
        "extraction_method": "scrape_html",
        "base_url": "https://www.ambito.com/"
    },
    # Medios Internacionales
    {
        "name": "Financial Times",
        "domain": "ft.com",
        "type": "international_news",
        "political_leaning": "Centro",
        "extraction_method": "scrape_html",
        "base_url": "https://www.ft.com/"
    },
    {
        "name": "The Economist",
        "domain": "economist.com",
        "type": "international_news",
        "political_leaning": "Centro-liberal",
        "extraction_method": "scrape_html",
        "base_url": "https://www.economist.com/"
    },
    {
        "name": "Reuters",
        "domain": "reuters.com",
        "type": "international_news_agency",
        "political_leaning": "Neutral",
        "extraction_method": "scrape_html",
        "base_url": "https://www.reuters.com/"
    },
    # Fuentes Oficiales del Estado (Argentina)
    {
        "name": "INDEC",
        "domain": "indec.gob.ar",
        "type": "official_data",
        "political_leaning": "Neutral",
        "extraction_method": "direct_download/api",
        "base_url": "https://www.indec.gob.ar/"
    },
    {
        "name": "Banco Central de la República Argentina (BCRA)",
        "domain": "bcra.gob.ar",
        "type": "official_data",
        "political_leaning": "Neutral",
        "extraction_method": "api_call",
        "base_url": "https://www.bcra.gob.ar/"
    },
    {
        "name": "Ministerio de Economía (Argentina)",
        "domain": "argentina.gob.ar/economia",
        "type": "official_data",
        "political_leaning": "Neutral",
        "extraction_method": "scrape_html",
        "base_url": "https://www.argentina.gob.ar/economia"
    },
]

def search_ddg(query: str) -> str:
    """Ejecuta una búsqueda en DuckDuckGo y devuelve los resultados."""
    with DDGS() as ddgs:
        results = ddgs.text(query, region="es-es", max_results=5)
        if results:
            return "\n".join(f"[{r['title']}]({r['href']})\n{r['body']}" for r in results)
    return "No se encontraron resultados."

def create_text_file(input_string: str) -> str:
    """Crea un archivo de texto en la ruta especificada con el contenido dado."""
    try:
        file_path, content = input_string.split(',', 1)
        file_path = file_path.strip()
        content = content.strip()
        safe_path = os.path.abspath(os.path.join(os.getcwd(), file_path))
        if os.path.commonprefix([os.getcwd(), safe_path]) != os.getcwd():
            return "Error: No se permite escribir archivos fuera del directorio de trabajo actual."
        with open(safe_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return f"Archivo '{file_path}' creado exitosamente."
    except Exception as e:
        return f"Error al crear el archivo: {e}. Asegúrate de que la entrada sea 'ruta/del/archivo.txt,contenido del archivo'."

def navigate_and_summarize_page(input_string: str) -> str:
    """
    Navega a una URL. Opcionalmente, espera a que un selector específico sea visible,
    un texto específico aparezca en la página, y/o añade un retardo tras la carga.
    Devuelve un resumen de los elementos interactivos (enlaces, botones y elementos clave del calendario) y el título de la página.
    """
    try:
        parts_dict = {}
        for part in input_string.split(','):
            if ':' in part:
                key, value = part.split(':', 1)
                parts_dict[key.strip()] = value.strip()

        url = parts_dict.get('url')
        wait_selector = parts_dict.get('wait_selector')
        wait_for_text = parts_dict.get('wait_for_text')
        post_render_delay = parts_dict.get('post_render_delay')

        if not url:
            return "Error: Se requiere una 'url' para navegar."

        with sync_playwright() as p:
            # CAMBIO CLAVE: headless=True para operación normal
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, timeout=20000)

            if wait_selector:
                page.wait_for_selector(wait_selector, timeout=20000)
            
            if wait_for_text:
                page.wait_for_selector(f'text="{wait_for_text}"', timeout=20000)
            
            if post_render_delay:
                try:
                    delay_ms = int(post_render_delay)
                    page.wait_for_timeout(delay_ms)
                except ValueError:
                    return f"Error: 'post_render_delay' debe ser un número en milisegundos, recibido: {post_render_delay}"

            page_title = page.title()
            interactive_elements = []
            
            # Extraer enlaces
            links = page.locator('a').all()
            for i, link_element in enumerate(links):
                text = link_element.inner_text()
                href = link_element.get_attribute('href')
                if text and href and not href.startswith('javascript:'):
                    clean_text = ' '.join(text.split()).strip()
                    if len(clean_text) > 1:
                        interactive_elements.append(f"  - Enlace (ID: link_{i}): '{clean_text}'")

            # Extraer botones
            buttons = page.locator('button').all()
            for i, button_element in enumerate(buttons):
                text = button_element.inner_text()
                if text:
                    clean_text = ' '.join(text.split()).strip()
                    if len(clean_text) > 1:
                        interactive_elements.append(f"  - Botón (ID: button_{i}): '{clean_text}'")

            # NUEVO: Extraer elementos específicos de FullCalendar o genéricos clickables
            # Selectores comunes de FullCalendar para botones de navegación y celdas de día
            calendar_specific_selectors = [
                '.fc-prev-button', '.fc-next-button', '.fc-toolbar-title',
                '.fc-daygrid-day-number', # números de día
                '.fc-daygrid-day', # celdas de día
                '[role="button"]', # elementos con rol de botón
                '[tabindex="0"]' # elementos focuseables que podrían ser interactivos
            ]
            
            for selector in calendar_specific_selectors:
                elements = page.locator(selector).all()
                for i, element in enumerate(elements):
                    text = element.inner_text()
                    if text:
                        clean_text = ' '.join(text.split()).strip()
                        if len(clean_text) > 1:
                            # Use a unique ID for each element type to avoid clashes
                            element_id = f"{selector.replace('.', '').replace('[', '').replace(']', '')}_{i}"
                            interactive_elements.append(f"  - Elemento Calendario (ID: {element_id}): '{clean_text}'")


            calendar_content = ""
            if wait_selector:
                try:
                    calendar_locator = page.locator(wait_selector)
                    calendar_text = calendar_locator.inner_text()
                    calendar_content = f"\nContenido visible del selector '{wait_selector}':\n{calendar_text[:1000]}...\n"
                except Exception as e:
                    calendar_content = f"\nNo se pudo extraer contenido del selector '{wait_selector}': {e}"


            browser.close()

            summary = f"Título de la página: '{page_title}'\n"
            summary += f"URL visitada: '{url}'\n"
            if calendar_content:
                summary += calendar_content
            if interactive_elements:
                summary += "\nElementos interactivos encontrados:\n" + "\n".join(interactive_elements)
            else:
                summary += "No se encontraron elementos interactivos claros en la página."
            return summary
            
    except PlaywrightTimeoutError:
        return f"Error: Timeout al intentar cargar la URL '{url}' o esperar al selector/texto."
    except Exception as e:
        return f"Error al navegar y analizar la página '{url}': {e}"

def analyze_political_news(topic: str) -> str:
    """
    Busca un tema político en los principales medios de noticias de Argentina,
    y devuelve un resumen comparativo de los hallazgos en formato JSON.
    """
    global _llm
    if _llm is None:
        _initialize_agent()

    print(f"🕵️  Analizando noticias políticas sobre: '{topic}'")
    
    # Filtramos las fuentes de noticias (nacionales e internacionales) y fuentes oficiales scrappeables para la búsqueda en DDG
    news_domains = [source["domain"] for source in SOURCES_CONFIG if source["type"] in ["national_news", "international_news", "international_news_agency", "official_data"] and source["extraction_method"] == "scrape_html"]
    
    # Buscamos en DDG para obtener URLs de artículos
    search_query = f"{topic} " + " OR ".join([f"site:{site}" for site in news_domains])
    print(f"   -> Buscando URLs con: '{search_query}'")
    
    with DDGS() as ddgs:
        results = ddgs.text(search_query, region="es-es", max_results=7) # Aumentar max_results para tener más opciones
        if not results:
            return f"No se encontraron noticias relevantes sobre '{topic}' en los principales medios."

    articles_to_summarize = []
    seen_urls = set()
    from urllib.parse import urlparse # Import here to ensure it's available
    for r in results:
        url = r['href']
        # Intentamos obtener el dominio para identificar el medio
        try:
            parsed_url = urlparse(url)
            domain = parsed_url.netloc
            # Buscar el nombre de la fuente en SOURCES_CONFIG
            source_info = next((s for s in SOURCES_CONFIG if s["domain"] in domain), None)
            media_outlet = source_info["name"] if source_info else domain
        except:
            media_outlet = "Desconocido"

        if url not in seen_urls:
            articles_to_summarize.append({"url": url, "title": r['title'], "media_outlet": media_outlet})
            seen_urls.add(url)
        if len(articles_to_summarize) >= 4: # Limitar a 4 artículos para el análisis comparativo
            break
            
    if not articles_to_summarize:
        return f"No se encontraron URLs de artículos únicas y relevantes para '{topic}'."

    individual_summaries = []
    for article_info in articles_to_summarize:
        print(f"   -> Obteniendo contenido de: {article_info['url']} ({article_info['media_outlet']})")
        article_text = get_clean_article_text(article_info['url'])
        
        if not article_text or "Error" in article_text:
            print(f"      No se pudo obtener el texto del artículo de {article_info['url']}. Saltando.")
            continue

        summary_prompt = (
            f"Resume el siguiente artículo de noticias sobre '{topic}' del medio '{article_info['media_outlet']}'. "
            "Enfócate en los hechos clave, citas directas, y cualquier ángulo o perspectiva específica presentada. "
            "Devuelve el resumen estrictamente en formato JSON con las claves: "
            "'media_outlet', 'title', 'url', 'summary_text' (un resumen conciso del artículo), "
            "'key_facts' (lista de 2-3 hechos importantes), y "
            "'media_angle' (un string breve que describa la perspectiva o enfoque del medio, si es discernible, o vacío si es neutral).\n\n"
            "Contenido del artículo:\n"
            "---------------------\n"
            f"{article_text}\n"
            "---------------------\n"
            "Genera la salida JSON."
        )
        try:
            llm_response = _llm.invoke(summary_prompt)
            clean_llm_response = llm_response.content.strip().replace("```json", "").replace("```", "").strip()
            summary_json = json.loads(clean_llm_response)
            individual_summaries.append(summary_json)
        except Exception as e:
            print(f"      Error al resumir el artículo de {article_info['url']}: {e}")
            continue

    if not individual_summaries:
        return f"No se pudieron generar resúmenes individuales para '{topic}'."

    # Paso 2: Comparar y sintetizar los resúmenes individuales
    comparison_prompt = (
        f"Analiza los siguientes resúmenes de artículos de noticias sobre '{topic}' de varios medios argentinos. "
        "Tu tarea es sintetizar esta información de manera neutral y objetiva. "
        "Devuelve la respuesta estrictamente en formato JSON con las siguientes claves:\n"
        "'common_facts' (una lista de strings con los hechos más importantes reportados consistentemente por la mayoría de los medios),\n"
        "'media_perspectives' (una lista de objetos, donde cada objeto contiene 'media_outlet', 'title', 'url', 'summary_text', 'key_facts', y 'media_angle' del resumen individual),\n"
        "'discrepancies' (un string que resuma cualquier diferencia significativa, omisión o ángulo único reportado por un medio en comparación con los otros; o un string vacío si no hay diferencias notables).\n"
        "Asegúrate de que 'media_perspectives' incluya todos los datos del resumen individual.\n\n"
        "Aquí están los resúmenes individuales:\n"
        "---------------------\n"
        f"{json.dumps(individual_summaries, indent=2)}\n"
        "---------------------\n"
        "Genera la salida JSON."
    )

    try:
        llm_comparison_response = _llm.invoke(comparison_prompt)
        clean_comparison_response = llm_comparison_response.content.strip().replace("```json", "").replace("```", "").strip()
        final_analysis_data = json.loads(clean_comparison_response)
        final_analysis_data['topic'] = topic # Asegurar que el topic esté presente en el nivel superior
        return f"ANALYSIS_JSON::{json.dumps(final_analysis_data)}"
    except Exception as e:
        print(f"Error al comparar y sintetizar las noticias: {e}")
        return f"Error al realizar el análisis comparativo: No se pudo generar o procesar el resumen en formato JSON. Error: {e}"

def get_clean_article_text(url: str) -> str:
    """Navega a una URL, descarga el HTML y extrae el texto principal del artículo."""
    try:
        # Añadir un User-Agent para simular una petición de navegador
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(url, timeout=10, headers=headers)
        response.raise_for_status() # Lanza una excepción para errores HTTP
        soup = BeautifulSoup(response.text, 'html.parser')

        # Intentar encontrar el contenido principal del artículo.
        # Ampliamos los selectores comunes para mayor cobertura.
        article_content = soup.find('article') or \
                          soup.find('main') or \
                          soup.find(class_='article-body') or \
                          soup.find(class_='post-content') or \
                          soup.find(class_='story-content') or \
                          soup.find(class_='entry-content')

        if article_content:
            # Eliminar scripts, estilos y otros elementos que no son texto de contenido.
            # Añadimos más elementos comunes que no forman parte del artículo principal.
            for unwanted in article_content(['script', 'style', 'nav', 'footer', 'header', '.ad', '.sidebar',
                                             '.comments', '.related-articles', '.share-buttons', '#comments',
                                             '[id*="comment"]', '[class*="comment"]', '[class*="share"]']):
                unwanted.extract()
            text = article_content.get_text(separator=' ', strip=True)
            return text[:5000] # Limitar a los primeros 5000 caracteres para no exceder el token
        else:
            # Si no se encuentra un 'article', intentar con el body y limpiar
            for unwanted in soup(['script', 'style', 'nav', 'footer', 'header', '.ad', '.sidebar',
                                  '.comments', '.related-articles', '.share-buttons', '#comments',
                                  '[id*="comment"]', '[class*="comment"]', '[class*="share"]']):
                unwanted.extract()
            text = soup.get_text(separator=' ', strip=True)
            return text[:5000] # Limitar a los primeros 5000 caracteres
    except requests.exceptions.RequestException as e:
        return f"Error de red o HTTP al obtener el artículo de '{url}': {e}"
    except Exception as e:
        return f"Error al extraer el texto del artículo de '{url}': {e}"

def get_bcra_economic_data(series_id: str) -> str:
    """
    Obtiene datos económicos específicos del Banco Central de la República Argentina (BCRA)
    a través de su API pública. La entrada es el ID de la serie de datos.
    Ejemplos: 'dolar_oficial', 'usd', 'inflacion_mensual', 'tasa_badlar_privadas'.
    """
    try:
        # La API del BCRA es extensa, este es un ejemplo simplificado para algunas series.
        # Es posible que se necesiten tokens para series más avanzadas o históricas.
        # Para este ejemplo, usaremos una aproximación a la URL más común para datos actuales.
        # Generalmente, datos como el dólar blue o inflación no están directamente en api.bcra.gob.ar
        # para acceso sin token. Una alternativa es usar APIs de terceros o scrapeo si no hay otra opción.
        # Sin embargo, la URL base oficial para consultas de series es api.bcra.gob.ar/estadisticas
        
        # Una forma más robusta sería una API como la de DolarAPI o similares para el dólar blue
        # Para el BCRA oficial, nos centraremos en datos que suelen estar más accesibles.
        # Por ejemplo, para obtener el tipo de cambio oficial:
        
        # BCRA no tiene un endpoint directo "dolar_oficial" público sin token en el formato que se espera.
        # Para fines de demostración y sin token, buscaremos URLs que ofrezcan datos relevantes.
        # Si se requiere precisión para series específicas, se debería investigar el endpoint exacto y autenticación.
        
        # Consideraremos una serie genérica que podría estar disponible sin autenticación
        # Por ejemplo, si buscamos una serie específica que se sabe es pública:
        
        # Simulación de un endpoint público para algunas series clave (ejemplo ilustrativo, no real del BCRA sin token)
        # La API real del BCRA a menudo requiere un token y tiene URLs más específicas como:
        # https://api.bcra.gob.ar/estadisticas/v1/datos/{id_serie}/{fecha_desde}/{fecha_hasta}

        # Para simplificar y dado que el acceso a la API del BCRA es más complejo,
        # para 'dolar_oficial' podemos intentar una API de terceros más amigable
        # o simular el resultado.
        
        if series_id == "dolar_oficial":
            # Usar una API de terceros más accesible para el dólar oficial, por ejemplo
            # Nota: Esto es un ejemplo. Una API real podría ser api.bluelytics.com.ar o similar.
            response = requests.get("https://api.bluelytics.com.ar/v2/latest", timeout=10)
            response.raise_for_status()
            data = response.json()
            return f"Dólar Oficial (venta): {data['oficial']['value_sell']} ARS"
        elif series_id == "dolar_blue":
            response = requests.get("https://api.bluelytics.com.ar/v2/latest", timeout=10)
            response.raise_for_status()
            data = response.json()
            return f"Dólar Blue (venta): {data['blue']['value_sell']} ARS"
        else:
            return f"Serie '{series_id}' no soportada directamente por esta herramienta del BCRA o requiere autenticación."

    except requests.exceptions.RequestException as e:
        return f"Error de red o HTTP al obtener datos del BCRA para '{series_id}': {e}"
    except Exception as e:
        return f"Error al procesar datos del BCRA para '{series_id}': {e}"

# Global agent executor and LLM to be initialized once
_agent_executor = None
_llm = None # New global LLM instance

def _initialize_agent():
    global _agent_executor, _llm
    if _agent_executor is not None and _llm is not None:
        return _agent_executor

    print("🤖 Inicializando Agente con Memoria...")

    # 2. EL CEREBRO (LLM)
    _llm = ChatGoogleGenerativeAI(model="gemini-2.5-pro", temperature=0, google_api_key=os.environ["GOOGLE_API_KEY"])

    # 3. LAS HERRAMIENTAS (TOOLS)
    tools = [
        Tool(
            name="Political News Analyzer",
            func=analyze_political_news,
            description="Muy útil para entender un tema de la política actual de Argentina. Busca en los principales medios, compara versiones y genera un resumen objetivo con diferencias destacadas. La entrada es el tema a analizar. Ejemplo: 'Ley Bases en el Senado'."
        ),
        Tool(
            name="DuckDuckGo Search",
            func=search_ddg,
            description="Útil para buscar información actualizada en internet sobre cualquier tema general (no usar para política de Argentina).",
        ),
        Tool(
            name="Text File Creator",
            func=create_text_file,
            description="Útil para crear un nuevo archivo de texto y escribir contenido en él. La entrada debe ser una cadena con la ruta del archivo, una coma, y luego el contenido a escribir. Ejemplo: 'mi_archivo.txt,Este es el contenido'."
        ),
        Tool(
            name="Social Media Idea Generator",
            func=generate_social_media_ideas,
            description="Genera ideas creativas para publicaciones de redes sociales. La entrada debe ser una cadena con 'topic: [tema], num_ideas: [cantidad]'. Ejemplo: 'topic: bodas en mi salón, num_ideas: 5'."
        ),
        Tool(
            name="Web Page Navigator",
            func=navigate_and_summarize_page,
            description="Útil para navegar a una dirección URL y obtener un resumen de su contenido y elementos interactivos (enlaces y botones). Puede esperar a que un selector CSS o un texto específico aparezca en la página, y/o añadir un retardo. La entrada es una cadena en formato 'url: [URL], wait_selector: [SELECTOR_CSS_OPCIONAL], wait_for_text: [TEXTO_OPCIONAL], post_render_delay: [MILISEGUNDOS_OPCIONAL]'. Ejemplo: 'url: https://elpatiodesalcedo.com.ar/calendario, wait_selector: .fc-view-harness', wait_for_text: 'Diciembre 2025', post_render_delay: 2000'."
        ),
        Tool(
            name="Article Content Extractor",
            func=get_clean_article_text,
            description="Útil para descargar una URL y extraer el texto principal (limpio) de un artículo de una página web. La entrada es la URL a visitar."
        ),
        Tool(
            name="BCRA Economic Data",
            func=get_bcra_economic_data,
            description="Útil para obtener datos económicos específicos del Banco Central de la República Argentina (BCRA). La entrada es el ID de la serie de datos. Ejemplos: 'dolar_oficial', 'dolar_blue'.",
        )
    ]

    # 4. EL AGENTE (ORQUESTADOR)
    # MODIFICACIÓN: Usamos un prompt diseñado para chat con memoria.
    prompt_template = hub.pull("hwchase17/react-chat")
    agent = create_react_agent(_llm, tools, prompt_template) # Use _llm here

    _agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        return_intermediate_steps=True  # ¡CAMBIO CLAVE!
    )
    return _agent_executor

def generate_social_media_ideas(input_string: str) -> str:
    """Genera ideas creativas para publicaciones de redes sociales."""
    global _llm
    if _llm is None:
        _initialize_agent() # Ensure LLM is initialized

    try:
        parts = {p.split(':')[0].strip(): p.split(':')[1].strip() for p in input_string.split(',')}
        topic = parts.get('topic')
        num_ideas = int(parts.get('num_ideas', 5))

        if not topic:
            return "Error: Se requiere un 'topic' para generar ideas."

        prompt = (f"Eres un experto en marketing digital para un salón de eventos. "
                  f"Genera {num_ideas} ideas creativas y atractivas para publicaciones de redes sociales (Instagram y Facebook) "
                  f"sobre el siguiente tema: '{topic}'. "
                  f"Las ideas deben ser variadas, originales y enfocadas en captar la atención de clientes potenciales "
                  f"que buscan un salón para sus eventos. Formatea la salida como una lista numerada.")
        
        response = _llm.invoke(prompt)
        return response.content
    except Exception as e:
        return f"Error al generar ideas para redes sociales: {e}. Asegúrate de que la entrada sea 'topic: [tema], num_ideas: [cantidad]'."

def get_agent_response(user_input: str, chat_history: list) -> str:
    """Obtiene una respuesta del agente basada en la entrada del usuario y el historial del chat."""
    agent_executor = _initialize_agent()
    try:
        response = agent_executor.invoke({
            "input": user_input,
            "chat_history": chat_history
        })

        # ¡CAMBIO CLAVE! Revisamos los pasos intermedios.
        if response.get("intermediate_steps"):
            last_step = response["intermediate_steps"][-1]
            tool_name = last_step[0].tool
            tool_observation = last_step[1]

            # Si la última herramienta fue el analizador político, devolvemos su salida directamente.
            if tool_name == "Political News Analyzer" and isinstance(tool_observation, str) and tool_observation.startswith("ANALYSIS_JSON::"):
                print("✅ Devolviendo salida directa del Analizador Político.")
                return tool_observation

        # Si no, devolvemos la respuesta final del agente.
        print("▶️  Devolviendo respuesta conversacional del agente.")
        return response['output']

    except Exception as e:
        import traceback
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("!!!         SE PRODUJO UN ERROR             !!!")
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print(f"Error en get_agent_response: {e}")
        traceback.print_exc()
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        return "Lo siento, hubo un error al procesar tu solicitud. Revisa la consola del servidor para más detalles."