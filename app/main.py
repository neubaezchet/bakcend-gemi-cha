from typing import List
from fastapi import FastAPI, UploadFile, Form, File
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
    import smtplib
    from email.mime.text import MIMEText

    from_email = "davidbaezaospino@gmail.com"
    smtp_server = "smtp.gmail.com"
    smtp_port = 587
    smtp_user = "davidbaezaospino@gmail.com"
    smtp_pass = "fmgn djcc xrav ujyf"

    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, [to_email], msg.as_string())
        server.quit()
        print(f"📧 Correo enviado a {to_email}")
        return True, None
    except Exception as e:
        print(f"Error enviando correo: {e}")
        return False, str(e)

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
    tipo: str = Form(...),
    archivos: List[UploadFile] = File(...)
):
    try:
        df = pd.read_excel(DATA_PATH)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"No se pudo leer el Excel: {e}"})

    empleado = df[df["cedula"] == int(cedula)] if not df.empty else None
    consecutivo = str(uuid.uuid4())[:8]
    links_archivos = []

    # Procesar todos los archivos recibidos
    for archivo in archivos:
        if archivo and archivo.filename:
            sufijo = Path(archivo.filename).suffix
            with tempfile.NamedTemporaryFile(delete=False, suffix=sufijo) as tmp:
                shutil.copyfileobj(archivo.file, tmp)
                tmp_path = Path(tmp.name)
            try:
                link = upload_to_drive(tmp_path, empresa.strip().upper(), cedula, tipo)
                links_archivos.append(link)
            except Exception as e:
                tmp_path.unlink(missing_ok=True)
                return JSONResponse(status_code=500, content={"error": f"Error subiendo archivo {archivo.filename}: {e}"})
            tmp_path.unlink()

    if empleado is not None and not empleado.empty:
        nombre = empleado.iloc[0]["nombre"]
        correo = empleado.iloc[0]["correo"]
        empresa_reg = empleado.iloc[0]["empresa"]
        body = f"Hola {nombre}, se ha registrado tu incapacidad en {empresa_reg} con consecutivo {consecutivo}.\nArchivos:\n" + "\n".join(links_archivos or ['No aplica'])
        sent, err = send_email(correo, "Registro de Incapacidad", body)
        sent2, err2 = send_email("xoblaxbaezaospino@gmail.com", "Copia Registro Incapacidad", body)
        if not sent or not sent2:
            return JSONResponse(status_code=500, content={"error": f"Error enviando correo: {err or err2}", "links_archivos": links_archivos})
        return {"status": "ok", "mensaje": "Registro exitoso", "consecutivo": consecutivo, "links_archivos": links_archivos}
    else:
        body = f"⚠️ Cédula {cedula} no encontrada. Empresa: {empresa}. Consecutivo: {consecutivo}."
        sent, err = send_email("xoblaxbaezaospino@gmail.com", "Alerta: Cédula no encontrada", body)
        if not sent:
            return JSONResponse(status_code=500, content={"error": f"Error enviando correo: {err}", "consecutivo": consecutivo})
        return {"status": "error", "mensaje": "Cédula no encontrada en el Excel", "consecutivo": consecutivo}

@app.get("/")
def root():
    return {"message": "✅ API funcionando en Render"}