from fastapi import FastAPI, UploadFile, Form
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import pandas as pd
import os, uuid, shutil, tempfile
from pathlib import Path
from app.drive_uploader import upload_to_drive

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "base_empleados.xlsx")

def send_email(to_email: str, subject: str, body: str):
    from_email = "noreply@incapacidades.com"
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email
    print(f"📧 Simulando envío de correo a {to_email}\nAsunto: {subject}\n{body}")

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
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/subir-incapacidad/")
async def subir_incapacidad(
    cedula: str = Form(...),
    empresa: str = Form(...),
    tipo: str = Form(...),          # ➜ nuevo
    archivo: UploadFile = None
):
    try:
        df = pd.read_excel(DATA_PATH)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"No se pudo leer el Excel: {e}"})

    empleado = df[df["cedula"] == int(cedula)] if not df.empty else None
    consecutivo = str(uuid.uuid4())[:8]
    link_archivo = None

    if archivo and archivo.filename:
        sufijo = Path(archivo.filename).suffix
        with tempfile.NamedTemporaryFile(delete=False, suffix=sufijo) as tmp:
            shutil.copyfileobj(archivo.file, tmp)
            tmp_path = Path(tmp.name)
        link_archivo = upload_to_drive(tmp_path, empresa.strip().upper(), cedula, tipo)
        tmp_path.unlink()

    if empleado is not None and not empleado.empty:
        nombre = empleado.iloc[0]["nombre"]
        correo = empleado.iloc[0]["correo"]
        empresa_reg = empleado.iloc[0]["empresa"]
        body = f"Hola {nombre}, se ha registrado tu incapacidad en {empresa_reg} con consecutivo {consecutivo}.\nArchivo: {link_archivo or 'No aplica'}"
        send_email(correo, "Registro de Incapacidad", body)
        send_email("xoblaxbaezaospino@gmail.com", "Copia Registro Incapacidad", body)
        return {"status": "ok", "mensaje": "Registro exitoso", "consecutivo": consecutivo, "link_archivo": link_archivo}
    else:
        body = f"⚠️ Cédula {cedula} no encontrada. Empresa: {empresa}. Consecutivo: {consecutivo}."
        send_email("xoblaxbaezaospino@gmail.com", "Alerta: Cédula no encontrada", body)
        return {"status": "error", "mensaje": "Cédula no encontrada en el Excel", "consecutivo": consecutivo}

@app.get("/")
def root():
    return {"message": "✅ API funcionando en Render"}