#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_liveness.py
Análisis de liveness detection con MediaPipe.
Compatible con:
  - API legacy  (mediapipe < 0.10.14): mp.solutions.face_mesh
  - API nueva   (mediapipe >= 0.10.14): mediapipe.tasks.python.vision.FaceLandmarker
"""

import sys
import json
import base64
import os

# ─────────────────────────────────────────────────────────────
# 1. IMPORTAR DEPENDENCIAS
# ─────────────────────────────────────────────────────────────
try:
    import numpy as np
    import cv2
    import mediapipe as mp
except ImportError as e:
    print(
        json.dumps(
            {
                "passed": False,
                "reason": (
                    f"Dependencia no instalada: {e}. "
                    "Ejecuta: pip install mediapipe opencv-python numpy"
                ),
                "frames_analyzed": 0,
                "detail": f"ImportError: {e}",
            }
        )
    )
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# 2. DETECTAR QUÉ API ESTÁ DISPONIBLE
# ─────────────────────────────────────────────────────────────
API_MODE = None  # 'legacy' | 'tasks'
MODELO_PATH = None  # Solo se usa en modo 'tasks'

# Intentar API legacy primero (mediapipe < 0.10.14)
if hasattr(mp, "solutions") and hasattr(mp.solutions, "face_mesh"):
    API_MODE = "legacy"
else:
    # Intentar nueva Tasks API (mediapipe >= 0.10.14)
    try:
        from mediapipe.tasks import python as _mp_py
        from mediapipe.tasks.python import vision as _mp_vision

        API_MODE = "tasks"
    except (ImportError, AttributeError):
        pass

if API_MODE is None:
    ver = getattr(mp, "__version__", "desconocida")
    print(
        json.dumps(
            {
                "passed": False,
                "reason": (
                    f"La versión de MediaPipe instalada ({ver}) no es compatible. "
                    "Prueba: pip install 'mediapipe>=0.10.0,<=0.10.13'  "
                    "o bien: pip install mediapipe==0.10.9"
                ),
                "frames_analyzed": 0,
                "detail": f"mediapipe version={ver}",
            }
        )
    )
    sys.exit(1)


# ─────────────────────────────────────────────────────────────
# 3. PARA TASKS API: ASEGURAR QUE EL MODELO ESTÉ DISPONIBLE
# ─────────────────────────────────────────────────────────────
if API_MODE == "tasks":
    MODELO_PATH = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "face_landmarker.task"
    )

    if not os.path.exists(MODELO_PATH):
        try:
            import urllib.request

            MODEL_URL = (
                "https://storage.googleapis.com/mediapipe-models/"
                "face_landmarker/face_landmarker/float16/1/face_landmarker.task"
            )
            sys.stderr.write(
                f"[INFO] Descargando modelo MediaPipe desde {MODEL_URL} ...\n"
            )
            urllib.request.urlretrieve(MODEL_URL, MODELO_PATH)
            sys.stderr.write("[INFO] Modelo descargado correctamente.\n")
        except Exception as e:
            print(
                json.dumps(
                    {
                        "passed": False,
                        "reason": (
                            "No se pudo descargar el modelo de MediaPipe (face_landmarker.task). "
                            "Descárgalo manualmente desde: "
                            "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task "
                            "y colócalo en la misma carpeta que este script. "
                            "Alternativamente instala una versión anterior: pip install mediapipe==0.10.9"
                        ),
                        "frames_analyzed": 0,
                        "detail": f"DownloadError: {e}",
                    }
                )
            )
            sys.exit(1)


# ─────────────────────────────────────────────────────────────
# 4. FUNCIONES DE CÁLCULO
# ─────────────────────────────────────────────────────────────

# Índices de landmarks del ojo para EAR
# [outer, upper-outer, upper-inner, inner, lower-inner, lower-outer]
OJO_IZQ = [33, 160, 158, 133, 153, 144]
OJO_DER = [362, 385, 387, 263, 373, 380]


def calcular_ear(landmarks, indices):
    """
    Eye Aspect Ratio (EAR) para detectar parpadeos.
    EAR = (A + B) / (2 * C)
    A, B = distancias verticales; C = distancia horizontal.
    Funciona con landmarks de ambas APIs (cualquier objeto con .x y .y).
    """
    p = [landmarks[i] for i in indices]

    A = np.sqrt((p[1].x - p[5].x) ** 2 + (p[1].y - p[5].y) ** 2)
    B = np.sqrt((p[2].x - p[4].x) ** 2 + (p[2].y - p[4].y) ** 2)
    C = np.sqrt((p[0].x - p[3].x) ** 2 + (p[0].y - p[3].y) ** 2)

    return float((A + B) / (2.0 * C)) if C > 1e-6 else 0.0


def decodificar_frame(frame_b64):
    """Decodifica un frame base64 a imagen OpenCV BGR. Retorna None si falla."""
    try:
        if "," in frame_b64:
            frame_b64 = frame_b64.split(",", 1)[1]
        img_bytes = base64.b64decode(frame_b64)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        return cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────
# 5. PROCESADORES DE FRAMES (uno por API)
# ─────────────────────────────────────────────────────────────


def extraer_landmarks_legacy(frames_b64):
    """
    Usa mp.solutions.face_mesh (mediapipe < 0.10.14).
    Retorna lista de listas de landmarks (o None si no hay cara en ese frame).
    """
    mp_face_mesh = mp.solutions.face_mesh
    resultados = []

    with mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5,
    ) as face_mesh:
        for frame_b64 in frames_b64:
            img = decodificar_frame(frame_b64)
            if img is None:
                resultados.append(None)
                continue

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            res = face_mesh.process(img_rgb)

            if res.multi_face_landmarks:
                resultados.append(res.multi_face_landmarks[0].landmark)
            else:
                resultados.append(None)

    return resultados


def extraer_landmarks_tasks(frames_b64):
    """
    Usa mediapipe.tasks.python.vision.FaceLandmarker (mediapipe >= 0.10.14).
    Retorna la misma estructura que extraer_landmarks_legacy.
    """
    base_opts = _mp_py.BaseOptions(model_asset_path=MODELO_PATH)
    opciones = _mp_vision.FaceLandmarkerOptions(
        base_options=base_opts,
        num_faces=1,
        min_face_detection_confidence=0.5,
        min_face_presence_confidence=0.5,
        min_tracking_confidence=0.5,
    )
    resultados = []

    with _mp_vision.FaceLandmarker.create_from_options(opciones) as detector:
        for frame_b64 in frames_b64:
            img = decodificar_frame(frame_b64)
            if img is None:
                resultados.append(None)
                continue

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=img_rgb)
            res = detector.detect(mp_img)

            if res.face_landmarks:
                resultados.append(res.face_landmarks[0])
            else:
                resultados.append(None)

    return resultados


def extraer_landmarks(frames_b64):
    """Despacha al procesador correcto según la API disponible."""
    if API_MODE == "legacy":
        return extraer_landmarks_legacy(frames_b64)
    else:
        return extraer_landmarks_tasks(frames_b64)


# ─────────────────────────────────────────────────────────────
# 6. ANÁLISIS PRINCIPAL
# ─────────────────────────────────────────────────────────────


def analizar_frames(frames_b64, challenge):
    """
    Extrae métricas de cada frame y evalúa si el challenge fue completado.
    Retorna un dict con: passed, reason, frames_analyzed, detail.
    """
    # Extraer landmarks de todos los frames
    todos_landmarks = extraer_landmarks(frames_b64)

    ear_values = []
    yaw_values = []
    mouth_values = []
    frames_con_cara = 0

    for lm in todos_landmarks:
        if lm is None:
            continue

        frames_con_cara += 1

        # EAR promedio (ambos ojos)
        ear_izq = calcular_ear(lm, OJO_IZQ)
        ear_der = calcular_ear(lm, OJO_DER)
        ear_values.append((ear_izq + ear_der) / 2.0)

        # Yaw: posición X normalizada de la punta de la nariz (landmark 1)
        yaw_values.append(float((lm[1].x - 0.5) * 100))

        # Apertura de boca: diferencia Y entre labio superior (13) e inferior (14)
        mouth_values.append(float(abs(lm[13].y - lm[14].y)))

    # ── Validar mínimo de frames con cara ──
    if frames_con_cara < 3:
        return {
            "passed": False,
            "reason": (
                f"No se detectó rostro en suficientes frames. "
                f"Cara detectada en {frames_con_cara}/{len(frames_b64)} frames (mínimo 3). "
                "Asegúrate de tener buena iluminación y estar frente a la cámara."
            ),
            "frames_analyzed": frames_con_cara,
            "detail": f"frames_total={len(frames_b64)} frames_cara={frames_con_cara}",
        }

    ear_arr = np.array(ear_values)
    yaw_arr = np.array(yaw_values)
    mouth_arr = np.array(mouth_values)

    # ── Anti-spoofing: EAR demasiado estable → imagen estática ──
    if len(ear_arr) > 4 and float(np.std(ear_arr)) < 0.0008:
        return {
            "passed": False,
            "reason": "Imagen estática detectada. Asegúrate de estar en vivo frente a la cámara.",
            "frames_analyzed": frames_con_cara,
            "detail": f"EAR std={np.std(ear_arr):.6f} (umbral: 0.0008)",
        }

    # ── Evaluar el challenge ──
    ch = challenge.lower()
    passed = False
    detail = ""
    reason = ""

    if "parpadea" in ch or "parpadeo" in ch:
        ear_min = float(np.min(ear_arr))
        ear_max = float(np.max(ear_arr))
        ear_diff = ear_max - ear_min
        passed = ear_min < 0.22 and ear_max > 0.25 and ear_diff > 0.06
        detail = f"EAR min={ear_min:.3f} max={ear_max:.3f} diff={ear_diff:.3f}"
        reason = (
            "Parpadeo detectado correctamente."
            if passed
            else f"No se detectó parpadeo completo. Cierra y abre bien los ojos. ({detail})"
        )

    elif "derecha" in ch:
        yaw_max = float(np.max(yaw_arr))
        passed = yaw_max > 12
        detail = f"Yaw máx={yaw_max:.1f}° (requiere >12°)"
        reason = (
            "Giro a la derecha detectado."
            if passed
            else f"Giro insuficiente a la derecha. Gira más la cabeza. ({detail})"
        )

    elif "izquierda" in ch:
        yaw_min = float(np.min(yaw_arr))
        passed = yaw_min < -12
        detail = f"Yaw mín={yaw_min:.1f}° (requiere <-12°)"
        reason = (
            "Giro a la izquierda detectado."
            if passed
            else f"Giro insuficiente a la izquierda. Gira más la cabeza. ({detail})"
        )

    elif "sonr" in ch:  # sonríe / sonrie / sonrisa
        mouth_range = float(np.max(mouth_arr) - np.min(mouth_arr))
        passed = mouth_range > 0.018
        detail = f"Rango boca={mouth_range:.4f} (requiere >0.018)"
        reason = (
            "Sonrisa detectada correctamente."
            if passed
            else f"Sonrisa insuficiente. Abre más la boca al sonreír. ({detail})"
        )

    else:
        reason = f"Desafío no reconocido: '{challenge}'"
        detail = "Válidos: parpadea, derecha, izquierda, sonríe"

    return {
        "passed": passed,
        "reason": reason,
        "frames_analyzed": frames_con_cara,
        "detail": detail,
    }


# ─────────────────────────────────────────────────────────────
# 7. PUNTO DE ENTRADA
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            raise ValueError("No se recibieron datos en stdin.")

        data = json.loads(raw)
        frames = data.get("frames", [])
        challenge = data.get("challenge", "")

        if not isinstance(frames, list) or not frames:
            raise ValueError("El campo 'frames' está vacío o no es un array.")
        if not challenge:
            raise ValueError("El campo 'challenge' está vacío.")

        resultado = analizar_frames(frames, challenge)
        print(json.dumps(resultado))

    except json.JSONDecodeError as e:
        print(
            json.dumps(
                {
                    "passed": False,
                    "reason": "Error al parsear el JSON de entrada.",
                    "frames_analyzed": 0,
                    "detail": f"JSONDecodeError: {e}",
                }
            )
        )
        sys.exit(1)

    except ValueError as e:
        print(
            json.dumps(
                {
                    "passed": False,
                    "reason": str(e),
                    "frames_analyzed": 0,
                    "detail": "Error de validación",
                }
            )
        )
        sys.exit(1)

    except Exception as e:
        print(
            json.dumps(
                {
                    "passed": False,
                    "reason": "Error interno durante el análisis. Revisa los logs del servidor.",
                    "frames_analyzed": 0,
                    "detail": f"Exception: {e}",
                }
            )
        )
        sys.exit(1)
