# SecureID — Liveness Detection

Mini proyecto de verificación facial con **Active Liveness Detection**.
Detecta si la persona frente a la cámara es real (no una foto, pantalla o dibujo) pidiéndole que realice una acción en vivo.

**Stack:** PHP + JavaScript Vanilla + Python (MediaPipe)

---

## Estructura del proyecto

```
liveness-demo/
├── index.html              ← Frontend (interfaz completa, CSS y JS inline)
├── verify_liveness.php     ← Backend PHP (puente entre frontend y Python)
├── verify_liveness.py      ← Script Python con análisis MediaPipe
├── requirements.txt        ← Dependencias Python
├── logs/                   ← Logs automáticos (se crea solo)
│   └── liveness.log
└── README.md
```

---

## Requisitos del servidor

| Componente | Versión mínima |
|-----------|----------------|
| PHP       | 7.4+ con `proc_open` habilitado |
| Python    | 3.8+ en el PATH del sistema |
| Servidor  | Apache / Nginx / `php -S` |
| Navegador | Chrome, Firefox o Edge modernos |

> **En producción:** Se requiere HTTPS para que `getUserMedia` funcione.

---

## Instalación

### 1. Instalar dependencias Python

```bash
cd liveness-demo
pip install -r requirements.txt
```

O con pip3 si tienes varias versiones de Python:

```bash
pip3 install -r requirements.txt
```

### 2. Verificar la instalación

```bash
python -c "import mediapipe, cv2, numpy; print('OK')"
```

Deberías ver `OK` sin errores.

---

## Cómo correr localmente

### Opción A: Servidor PHP integrado

```bash
cd liveness-demo
php -S localhost:8000
```

Abrir en el navegador: **http://localhost:8000**

> Nota: `getUserMedia` puede requerir HTTPS en algunos navegadores al correr en localhost.
> Si tienes problemas, usa Chrome con el flag `--unsafely-treat-insecure-origin-as-secure=http://localhost:8000`.

### Opción B: XAMPP / Apache

1. Copia la carpeta `liveness-demo/` dentro de `htdocs/`
2. Inicia Apache desde el panel de XAMPP
3. Abre: **http://localhost/liveness-demo/**

---

## Desafíos disponibles

El sistema elige uno aleatoriamente en cada verificación:

| Desafío | Descripción | Umbral de detección |
|---------|------------|---------------------|
| **Parpadea 2 veces** | EAR baja < 0.22 y sube > 0.25 | diff EAR > 0.06 |
| **Gira a la derecha** | Punta de nariz se desplaza a la derecha | Yaw máx > 12° |
| **Gira a la izquierda** | Punta de nariz se desplaza a la izquierda | Yaw mín < -12° |
| **Sonríe** | Apertura de boca aumenta | Rango apertura > 0.018 |

### Anti-spoofing
Si el `std` del EAR en más de 4 frames es menor a `0.0008`, se rechaza como imagen estática (foto o pantalla).

---

## Posibles errores y soluciones

### `proc_open` deshabilitado en PHP

**Error:** `No se pudo iniciar el proceso Python`

**Solución:** Editar `php.ini` y asegurarse de que `proc_open` **no** esté en `disable_functions`:

```ini
; Buscar esta línea y eliminar proc_open de la lista:
disable_functions = ...
```

Reiniciar Apache/PHP después del cambio.

---

### Python no encontrado en PATH

**Error:** `Python no encontrado en el PATH del sistema`

**Solución en Windows:**

1. Abrir **Panel de Control** → **Sistema** → **Variables de entorno**
2. En `PATH` agregar la ruta de Python, p.ej.: `C:\Python312\` y `C:\Python312\Scripts\`
3. Reiniciar Apache / XAMPP para que tome los cambios del entorno

**Verificar:**
```bash
python --version
# o
python3 --version
```

---

### MediaPipe no instalado

**Error:** `Dependencia no instalada: No module named 'mediapipe'`

**Solución:**
```bash
pip install mediapipe>=0.10.0 opencv-python>=4.8.0 numpy>=1.24.0
```

Verificar que estás usando el mismo Python que tiene Apache/PHP en el PATH.

---

### Permisos en carpeta `logs/`

**Error:** No se escriben los logs

**Solución:**
```bash
chmod 755 logs/
# o en Windows: dar permisos de escritura al usuario del servidor (IUSR o SYSTEM)
```

---

### Cámara bloqueada por el navegador

**Síntoma:** El navegador no pide permiso de cámara o muestra error

**Causas comunes:**
- Sitio en HTTP en lugar de HTTPS (requerido en producción)
- Permisos de cámara bloqueados para el sitio en la configuración del navegador
- Otra aplicación usando la cámara (Zoom, Teams, etc.)

**Solución:**
- En producción: configurar certificado SSL (Let's Encrypt)
- En desarrollo: usar `localhost` (Chrome lo permite en HTTP)
- Liberar la cámara cerrando otras aplicaciones

---

### Rostro no detectado (pocos frames con cara)

**Síntoma:** `"No se detectó rostro en suficientes frames"`

**Causas:**
- Mala iluminación (muy oscuro o contraluces)
- Rostro muy alejado de la cámara
- Lentes de sol u objetos cubriendo el rostro

**Solución:** Mejorar iluminación y acercarse a la cámara.

---

## Notas de seguridad (producción)

1. **HTTPS obligatorio:** `getUserMedia` requiere contexto seguro
2. **Validar frames en servidor:** Verificar que sean imágenes JPEG/PNG válidas antes de procesar
3. **Rate limiting:** Agregar límite de peticiones al endpoint PHP para evitar abusos
4. **Logs:** El archivo `logs/liveness.log` no debe ser accesible públicamente. Agregar a `.htaccess`:
   ```apache
   <Directory "logs">
       Deny from all
   </Directory>
   ```
5. **Tamaño de payload:** Los ~25 frames pueden pesar hasta ~2MB. Verificar que `post_max_size` y `upload_max_filesize` en `php.ini` sean suficientes (8MB+)

---

## Comportamiento esperado

| Escenario | Resultado esperado |
|-----------|-------------------|
| Persona real completa el reto | ✅ `passed: true` |
| Foto impresa frente a la cámara | ❌ "Imagen estática detectada" |
| Pantalla con video de rostro | ❌ EAR std demasiado bajo |
| No hay rostro en la cámara | ❌ "No se detectó rostro" |
| Persona no completa el reto | ❌ "No se completó: [detalle]" |
