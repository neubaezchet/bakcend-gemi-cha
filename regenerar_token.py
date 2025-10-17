"""
Script para regenerar el REFRESH_TOKEN de Google Drive
Ejecutar en la carpeta del backend
"""

from google_auth_oauthlib.flow import InstalledAppFlow

# Tus credenciales desde el .env
CLIENT_ID = "680515257259-9bvnl3cu8cgpit0oak7ljrjvdh8q2rmb.apps.googleusercontent.com"
CLIENT_SECRET = "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"

SCOPES = ['https://www.googleapis.com/auth/drive.file']

def main():
    print("=" * 70)
    print("🔧 REGENERANDO REFRESH TOKEN DE GOOGLE DRIVE")
    print("=" * 70)
    print()
    print("Se abrirá una ventana del navegador para autorizar el acceso.")
    print("Inicia sesión con: davidbaezaospino@gmail.com")
    print()
    input("Presiona ENTER para continuar...")
    
    # Configuración del cliente OAuth
    client_config = {
        "installed": {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "redirect_uris": ["http://localhost:8080/"],
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    
    try:
        # Iniciar flujo OAuth
        flow = InstalledAppFlow.from_client_config(
            client_config,
            scopes=SCOPES
        )
        
        # Esto abrirá el navegador automáticamente
        creds = flow.run_local_server(port=8080)
        
        print()
        print("=" * 70)
        print("✅ AUTORIZACIÓN EXITOSA")
        print("=" * 70)
        print()
        print("📋 COPIA ESTE REFRESH TOKEN:")
        print()
        print("─" * 70)
        print(creds.refresh_token)
        print("─" * 70)
        print()
        
        # Guardar en archivo para no perderlo
        with open("NUEVO_REFRESH_TOKEN.txt", "w") as f:
            f.write("GOOGLE_REFRESH_TOKEN=" + creds.refresh_token)
        
        print("✅ Token también guardado en: NUEVO_REFRESH_TOKEN.txt")
        print()
        print("📝 PASOS SIGUIENTES:")
        print("1. Copia el token de arriba")
        print("2. Ve a: https://dashboard.render.com")
        print("3. Selecciona: bakcend-gemi-cha-2")
        print("4. Settings → Environment")
        print("5. Busca: GOOGLE_REFRESH_TOKEN")
        print("6. Pega el nuevo token")
        print("7. Guarda (Save Changes)")
        print("8. Espera 1-2 minutos a que se reinicie")
        print()
        print("=" * 70)
        
    except Exception as e:
        print()
        print("❌ ERROR:")
        print(str(e))
        print()
        if "redirect_uri_mismatch" in str(e):
            print("⚠️ Error de redirect_uri. Usa el Método B (OAuth Playground)")
            print("   https://developers.google.com/oauthplayground/")

if __name__ == "__main__":
    main()