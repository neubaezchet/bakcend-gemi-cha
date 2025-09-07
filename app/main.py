from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware  # ➜ AGREGAR
import pandas as pd
import os, uuid, smtplib
from email.mime.text import MIMEText

app = FastAPI()

# ➜ AGREGAR CONFIGURACIÓN CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En producción, especifica los dominios permitidos
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

# ➜ AGREGAR ENDPOINT PARA BUSCAR EMPLEADOS
@app.get("/empleados/{cedula}")
def obtener_empleado(cedula: str):
    try:
        df = pd.read_excel(DATA_PATH)
        empleado = df[df["cedula"] == int(cedula)]
        
        if empleado.empty:
            return JSONResponse(status_code=404, content={"error": "Empleado no encontrado"})
        
        return {
            "nombre": empleado.iloc[0]["nombre"],
            "empresa": empleado.iloc[0]["empresa"],
            "correo": empleado.iloc[0]["correo"]
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Error al buscar empleado: {str(e)}"})

# ➜ TU CÓDIGO EXISTENTE (pero sin el segundo app = FastAPI())
@app.post("/subir-incapacidad/")
async def subir_incapacidad(cedula: str = Form(...), empresa: str = Form(...), archivo: UploadFile = None):
    try:
        df = pd.read_excel(DATA_PATH)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"No se pudo leer el Excel: {e}"})

    empleado = df[df["cedula"] == int(cedula)] if not df.empty else None
    consecutivo = str(uuid.uuid4())[:8]

    if empleado is not None and not empleado.empty:
        nombre = empleado.iloc[0]["nombre"]
        correo = empleado.iloc[0]["correo"]
        empresa_reg = empleado.iloc[0]["empresa"]

        body = f"Hola {nombre}, se ha registrado tu incapacidad en {empresa_reg} con consecutivo {consecutivo}."
        send_email(correo, "Registro de Incapacidad", body)
        send_email("xoblaxbaezaospino@gmail.com", "Copia Registro Incapacidad", body)

        return {"status": "ok", "mensaje": "Registro exitoso", "consecutivo": consecutivo}
    else:
        body = f"⚠️ No se encontró la cédula {cedula} en la base de empleados. Empresa reportada: {empresa}. Consecutivo: {consecutivo}."
        send_email("xoblaxbaezaospino@gmail.com", "Alerta: Cédula no encontrada", body)
        return {"status": "error", "mensaje": "Cédula no encontrada en el Excel", "consecutivo": consecutivo}

def send_email(to_email: str, subject: str, body: str):
    from_email = "noreply@incapacidades.com"
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    print(f"📧 Simulando envío de correo a {to_email}\nAsunto: {subject}\n{body}")

@app.get("/")
def root():
    return {"message": "✅ API funcionando en Render"}
