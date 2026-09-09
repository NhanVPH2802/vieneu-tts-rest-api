#!/usr/bin/env bash
set -Eeuo pipefail

# ============================================================
# VieNeu-TTS + REST API automatic installer
# Target: Ubuntu Server 24.04
# ============================================================

if [[ "${EUID}" -ne 0 ]]; then
    echo "ERROR: Hay chay script bang sudo:"
    echo "  sudo bash scripts/install.sh"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

VERSION_FILE="${REPO_DIR}/VERSION"
API_REQUIREMENTS="${REPO_DIR}/requirements-api.txt"

VIENEU_DIR="/opt/VieNeu-TTS"
API_DIR="/opt/vieneu-api"

SERVICE_USER="vieneu"
SERVICE_GROUP="vieneu"

ENV_FILE="/etc/vieneu-api.env"

echo
echo "=========================================="
echo " VieNeu-TTS REST API Installer"
echo "=========================================="
echo

# ------------------------------------------------------------
# 1. Validate release files
# ------------------------------------------------------------

for file in \
    "${VERSION_FILE}" \
    "${API_REQUIREMENTS}" \
    "${REPO_DIR}/api/app.py" \
    "${REPO_DIR}/api/voice-manager.html" \
    "${REPO_DIR}/systemd/vieneu.service" \
    "${REPO_DIR}/systemd/vieneu-api.service" \
    "${REPO_DIR}/systemd/temp.conf"
do
    if [[ ! -f "${file}" ]]; then
        echo "ERROR: Thieu file: ${file}"
        exit 1
    fi
done

# shellcheck disable=SC1090
source "${VERSION_FILE}"

if [[ -z "${UPSTREAM_REPO:-}" ]]; then
    echo "ERROR: UPSTREAM_REPO trong VERSION dang rong."
    exit 1
fi

if [[ -z "${UPSTREAM_COMMIT:-}" ]]; then
    echo "ERROR: UPSTREAM_COMMIT trong VERSION dang rong."
    exit 1
fi

echo "VieNeu repository:"
echo "  ${UPSTREAM_REPO}"
echo
echo "VieNeu commit:"
echo "  ${UPSTREAM_COMMIT}"
echo

# ------------------------------------------------------------
# 2. Do not overwrite an existing installation
# ------------------------------------------------------------

if [[ -e "${VIENEU_DIR}" ]]; then
    echo "ERROR: ${VIENEU_DIR} da ton tai."
    echo "Script nay duoc thiet ke cho server cai moi."
    exit 1
fi

if [[ -e "${API_DIR}" ]]; then
    echo "ERROR: ${API_DIR} da ton tai."
    echo "Script nay duoc thiet ke cho server cai moi."
    exit 1
fi

# ------------------------------------------------------------
# 3. Install Ubuntu packages
# ------------------------------------------------------------

echo "[1/11] Cai dat system packages..."

export DEBIAN_FRONTEND=noninteractive

apt-get update

apt-get install -y \
    git \
    curl \
    wget \
    jq \
    ffmpeg \
    openssl \
    ca-certificates \
    build-essential \
    python3 \
    python3-dev \
    python3-venv \
    python3-pip \
    libsndfile1

# ------------------------------------------------------------
# 4. Create service user
# ------------------------------------------------------------

echo "[2/11] Tao user vieneu..."

if ! id "${SERVICE_USER}" >/dev/null 2>&1; then
    useradd \
        --system \
        --create-home \
        --home-dir /home/vieneu \
        --shell /bin/bash \
        "${SERVICE_USER}"
fi

# ------------------------------------------------------------
# 5. Clone VieNeu-TTS
# ------------------------------------------------------------

echo "[3/11] Clone VieNeu-TTS..."

clone_public_repo() {
    GIT_TERMINAL_PROMPT=0 \
        git clone "${UPSTREAM_REPO}" "${VIENEU_DIR}"
}

clone_private_repo() {
    local gh_pat="${GH_PAT:-}"
    local auth_b64

    if [[ -z "${gh_pat}" ]]; then
        echo
        echo "Repository dang Private."
        echo "Nhap GitHub PAT co quyen Read repository."
        echo

        read -r -s -p "GitHub PAT: " gh_pat
        echo
    fi

    if [[ -z "${gh_pat}" ]]; then
        echo "ERROR: PAT rong."
        exit 1
    fi

    auth_b64="$(
        printf 'x-access-token:%s' "${gh_pat}" \
        | base64 -w0
    )"

    GIT_TERMINAL_PROMPT=0 \
        git \
        -c "http.extraHeader=Authorization: Basic ${auth_b64}" \
        clone \
        "${UPSTREAM_REPO}" \
        "${VIENEU_DIR}"

    unset auth_b64
}

if ! clone_public_repo; then
    rm -rf "${VIENEU_DIR}"
    clone_private_repo
fi

git -C "${VIENEU_DIR}" remote set-url origin "${UPSTREAM_REPO}"

echo "Checkout commit..."

git -C "${VIENEU_DIR}" checkout "${UPSTREAM_COMMIT}"

CURRENT_COMMIT="$(
    git -C "${VIENEU_DIR}" rev-parse HEAD
)"

if [[ "${CURRENT_COMMIT}" != "${UPSTREAM_COMMIT}" ]]; then
    echo "ERROR: Commit checkout khong dung."
    echo "Expected: ${UPSTREAM_COMMIT}"
    echo "Actual:   ${CURRENT_COMMIT}"
    exit 1
fi

chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${VIENEU_DIR}"

# ------------------------------------------------------------
# 6. Install VieNeu-TTS Python environment
# ------------------------------------------------------------

echo "[4/11] Cai dat VieNeu-TTS..."

sudo -u "${SERVICE_USER}" \
    python3 -m venv "${VIENEU_DIR}/.venv"

sudo -u "${SERVICE_USER}" \
    "${VIENEU_DIR}/.venv/bin/python" \
    -m pip install --upgrade \
    pip \
    setuptools \
    wheel

sudo -u "${SERVICE_USER}" \
    "${VIENEU_DIR}/.venv/bin/pip" \
    install -e "${VIENEU_DIR}"

if [[ ! -x "${VIENEU_DIR}/.venv/bin/vieneu-web" ]]; then
    echo "ERROR: Khong tim thay:"
    echo "  ${VIENEU_DIR}/.venv/bin/vieneu-web"
    echo
    echo "VieNeu-TTS co the da thay doi cach cai dat."
    exit 1
fi

# ------------------------------------------------------------
# 7. Install PyTorch CPU for voice cloning
# ------------------------------------------------------------

echo "[5/11] Cai PyTorch CPU cho Voice Cloning..."

sudo -u "${SERVICE_USER}" \
    "${VIENEU_DIR}/.venv/bin/python" \
    -m pip install \
    torch \
    torchaudio \
    --index-url https://download.pytorch.org/whl/cpu

sudo -u "${SERVICE_USER}" \
    "${VIENEU_DIR}/.venv/bin/python" - <<'PY'
import torch
import torchaudio

print("Torch:", torch.__version__)
print("Torchaudio:", torchaudio.__version__)
print("CUDA:", torch.cuda.is_available())
PY

# ------------------------------------------------------------
# 8. Configure Gradio temp directory
# ------------------------------------------------------------

echo "[6/11] Tao Gradio temp directory..."

mkdir -p \
    "${VIENEU_DIR}/tmp/gradio"

chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${VIENEU_DIR}/tmp"

chmod -R 775 \
    "${VIENEU_DIR}/tmp"

# ------------------------------------------------------------
# 9. Install REST API
# ------------------------------------------------------------

echo "[7/11] Cai REST API..."

mkdir -p \
    "${API_DIR}" \
    "${API_DIR}/custom_voices" \
    "${API_DIR}/upload_tmp" \
    "${API_DIR}/tmp" \
    "${API_DIR}/output"

cp \
    "${REPO_DIR}/api/app.py" \
    "${API_DIR}/app.py"

cp \
    "${REPO_DIR}/api/voice-manager.html" \
    "${API_DIR}/voice-manager.html"

chown -R \
    "${SERVICE_USER}:${SERVICE_GROUP}" \
    "${API_DIR}"

sudo -u "${SERVICE_USER}" \
    python3 -m venv "${API_DIR}/.venv"

sudo -u "${SERVICE_USER}" \
    "${API_DIR}/.venv/bin/python" \
    -m pip install --upgrade \
    pip \
    setuptools \
    wheel

sudo -u "${SERVICE_USER}" \
    "${API_DIR}/.venv/bin/pip" \
    install \
    -r "${API_REQUIREMENTS}"

sudo -u "${SERVICE_USER}" \
    "${API_DIR}/.venv/bin/pip" \
    install python-multipart

"${API_DIR}/.venv/bin/python" \
    -m py_compile \
    "${API_DIR}/app.py"

# ------------------------------------------------------------
# 10. Generate API configuration
# ------------------------------------------------------------

echo "[8/11] Tao REST API configuration..."

API_KEY="$(openssl rand -hex 32)"

cat > "${ENV_FILE}" <<EOF
VIENEU_GRADIO_URL=http://127.0.0.1:7860
VIENEU_API_KEY=${API_KEY}
VIENEU_VOICES_FILE=/opt/VieNeu-TTS/src/vieneu/assets/voices_v3_turbo.json
VIENEU_CUSTOM_VOICES_DIR=/opt/vieneu-api/custom_voices
VIENEU_UPLOAD_TMP_DIR=/opt/vieneu-api/upload_tmp
EOF

chown root:root "${ENV_FILE}"
chmod 600 "${ENV_FILE}"

# ------------------------------------------------------------
# 11. Install systemd services
# ------------------------------------------------------------

echo "[9/11] Cai systemd services..."

install \
    -m 0644 \
    "${REPO_DIR}/systemd/vieneu.service" \
    /etc/systemd/system/vieneu.service

install \
    -m 0644 \
    "${REPO_DIR}/systemd/vieneu-api.service" \
    /etc/systemd/system/vieneu-api.service

mkdir -p \
    /etc/systemd/system/vieneu.service.d

install \
    -m 0644 \
    "${REPO_DIR}/systemd/temp.conf" \
    /etc/systemd/system/vieneu.service.d/temp.conf

# Make sure REST API always starts after VieNeu-TTS.
mkdir -p \
    /etc/systemd/system/vieneu-api.service.d

cat > \
    /etc/systemd/system/vieneu-api.service.d/override.conf <<'EOF'
[Unit]
Requires=vieneu.service
After=network-online.target vieneu.service
Wants=network-online.target
EOF

systemctl daemon-reload

systemctl enable \
    vieneu.service \
    vieneu-api.service

# ------------------------------------------------------------
# 12. Start VieNeu-TTS
# ------------------------------------------------------------

echo "[10/11] Khoi dong VieNeu-TTS..."

systemctl restart vieneu.service

echo "Cho VieNeu-TTS mo cong 7860..."

VIENEU_READY=0

for _ in $(seq 1 90); do
    if curl \
        -fsS \
        http://127.0.0.1:7860/config \
        >/dev/null 2>&1
    then
        VIENEU_READY=1
        break
    fi

    sleep 5
done

if [[ "${VIENEU_READY}" -ne 1 ]]; then
    echo
    echo "ERROR: VieNeu-TTS khong khoi dong thanh cong."
    echo
    systemctl status vieneu.service --no-pager || true
    echo
    journalctl \
        -u vieneu.service \
        -n 100 \
        --no-pager || true
    exit 1
fi

echo "VieNeu-TTS OK."

# ------------------------------------------------------------
# 13. Start REST API and preload model
# ------------------------------------------------------------

echo "[11/11] Khoi dong REST API..."

systemctl restart vieneu-api.service

echo "Cho REST API preload model..."

API_READY=0
HEALTH_RESULT=""

for _ in $(seq 1 120); do
    HEALTH_RESULT="$(
        curl \
            -fsS \
            http://127.0.0.1:8000/api/health \
            2>/dev/null || true
    )"

    if [[ -n "${HEALTH_RESULT}" ]] && \
       echo "${HEALTH_RESULT}" \
       | jq -e '.status == "ok"' \
       >/dev/null 2>&1
    then
        API_READY=1
        break
    fi

    sleep 5
done

if [[ "${API_READY}" -ne 1 ]]; then
    echo
    echo "ERROR: REST API chua san sang."
    echo
    echo "Health:"
    echo "${HEALTH_RESULT}"
    echo
    systemctl status vieneu-api.service --no-pager || true
    echo
    journalctl \
        -u vieneu-api.service \
        -n 150 \
        --no-pager || true
    exit 1
fi

SERVER_IP="$(
    hostname -I \
    | awk '{print $1}'
)"

echo
echo "=========================================="
echo " CAI DAT HOAN TAT"
echo "=========================================="
echo
echo "VieNeu WebUI:"
echo "  http://${SERVER_IP}:7860"
echo
echo "REST API:"
echo "  http://${SERVER_IP}:8000"
echo
echo "Swagger:"
echo "  http://${SERVER_IP}:8000/docs"
echo
echo "Voice Manager:"
echo "  http://${SERVER_IP}:8000/voice-manager"
echo
echo "API Key:"
echo "  ${API_KEY}"
echo
echo "API Key duoc luu tai:"
echo "  ${ENV_FILE}"
echo
echo "Health:"
echo "${HEALTH_RESULT}" | jq .
echo
echo "Autostart:"
echo "  vieneu.service     : $(systemctl is-enabled vieneu.service)"
echo "  vieneu-api.service : $(systemctl is-enabled vieneu-api.service)"
echo
echo "Khuyen nghi Voice Cloning:"
echo "  RAM toi thieu: 8 GB"
echo "  Reference WAV: 3 - 8 giay"
echo
