const flashEl = document.getElementById("flash");
const nodesTable = document.getElementById("nodes-table");
const importForm = document.getElementById("import-form");
const settingsForm = document.getElementById("settings-form");
const editDialog = document.getElementById("edit-dialog");
const editForm = document.getElementById("edit-form");
const deleteDialog = document.getElementById("delete-dialog");
const deleteCopy = document.getElementById("delete-copy");
const confirmDeleteButton = document.getElementById("confirm-delete");
let pendingDeleteNode = null;

function showFlash(message, type = "success") {
  flashEl.textContent = message;
  flashEl.className = `flash flash-${type}`;
}

function hideFlash() {
  flashEl.textContent = "";
  flashEl.className = "flash hidden";
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
    ...options,
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || "请求失败");
  }
  return data;
}

function formToObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

function fillStats(nodes) {
  const xrayCount = nodes.filter((node) => node.kernel === "xray").length;
  const singboxCount = nodes.filter((node) => node.kernel === "sing-box").length;
  document.getElementById("stat-nodes").textContent = String(nodes.length);
  document.getElementById("stat-xray").textContent = String(xrayCount);
  document.getElementById("stat-singbox").textContent = String(singboxCount);
}

function fillSettings(settings) {
  settingsForm.elements.xray_log_level.value = settings.xray_log_level;
  settingsForm.elements.singbox_log_level.value = settings.singbox_log_level;
}

function openEdit(node) {
  editForm.elements.id.value = node.id;
  editForm.elements.name_override.value = node.name || "";
  editForm.elements.local_port.value = node.local_port || "";
  editForm.elements.kernel.value = node.kernel || "xray";
  editForm.elements.share_link.value = node.link || "";
  editDialog.showModal();
}

function openDeleteDialog(node) {
  pendingDeleteNode = node;
  deleteCopy.textContent = `确认删除“${node.name}”吗？删除后会自动重载对应运行时配置。`;
  confirmDeleteButton.disabled = false;
  confirmDeleteButton.textContent = "确认删除";
  deleteDialog.showModal();
}

function closeDeleteDialog() {
  pendingDeleteNode = null;
  deleteDialog.close();
}

function renderNodes(nodes) {
  if (!nodes.length) {
    nodesTable.innerHTML = '<tr><td colspan="4" class="node-meta">当前还没有节点。</td></tr>';
    return;
  }

  nodesTable.innerHTML = nodes
    .map((node) => {
      const meta = [node.kernel, node.protocol, node.network].filter(Boolean).join(" / ");
      const socks = `socks5://127.0.0.1:${node.local_port}#${node.name}`;
      return `
        <tr>
          <td>
            <div class="node-title">${escapeHtml(node.name)}</div>
            <div class="node-meta">${escapeHtml(meta)}</div>
          </td>
          <td class="mono">${escapeHtml(socks)}</td>
          <td>${escapeHtml(node.address)}:${escapeHtml(node.port)}</td>
          <td>
            <div class="row-actions">
              <button class="button button-ghost" data-action="edit" data-id="${escapeHtml(node.id)}">编辑</button>
              <button class="button button-danger" data-action="delete" data-id="${escapeHtml(node.id)}">删除</button>
            </div>
          </td>
        </tr>
      `;
    })
    .join("");

  nodesTable.querySelectorAll("[data-action='edit']").forEach((button) => {
    button.addEventListener("click", () => {
      const node = nodes.find((item) => item.id === button.dataset.id);
      if (node) {
        openEdit(node);
      }
    });
  });

  nodesTable.querySelectorAll("[data-action='delete']").forEach((button) => {
    button.addEventListener("click", () => {
      const node = nodes.find((item) => item.id === button.dataset.id);
      if (!node) {
        return;
      }
      openDeleteDialog(node);
    });
  });
}

async function loadState() {
  const state = await api("/api/state");
  renderNodes(state.nodes);
  fillStats(state.nodes);
  fillSettings(state.settings);
  importForm.elements.local_port.value = state.next_local_port;
}

importForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/nodes/import", {
      method: "POST",
      body: JSON.stringify(formToObject(importForm)),
    });
    showFlash(result.message);
    importForm.reset();
    await loadState();
  } catch (error) {
    showFlash(error.message, "error");
  }
});

settingsForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/settings", {
      method: "POST",
      body: JSON.stringify(formToObject(settingsForm)),
    });
    showFlash(result.message);
    await loadState();
  } catch (error) {
    showFlash(error.message, "error");
  }
});

editForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    const result = await api("/api/nodes/edit", {
      method: "POST",
      body: JSON.stringify(formToObject(editForm)),
    });
    editDialog.close();
    showFlash(result.message);
    await loadState();
  } catch (error) {
    showFlash(error.message, "error");
  }
});

document.getElementById("refresh-button").addEventListener("click", async () => {
  hideFlash();
  try {
    await loadState();
  } catch (error) {
    showFlash(error.message, "error");
  }
});

document.getElementById("close-edit").addEventListener("click", () => {
  editDialog.close();
});

document.getElementById("cancel-delete").addEventListener("click", closeDeleteDialog);

confirmDeleteButton.addEventListener("click", async () => {
  if (!pendingDeleteNode) {
    return;
  }

  confirmDeleteButton.disabled = true;
  confirmDeleteButton.textContent = "删除中...";
  try {
    const result = await api("/api/nodes/delete", {
      method: "POST",
      body: JSON.stringify({ id: pendingDeleteNode.id }),
    });
    closeDeleteDialog();
    showFlash(result.message);
    await loadState();
  } catch (error) {
    confirmDeleteButton.disabled = false;
    confirmDeleteButton.textContent = "确认删除";
    showFlash(error.message, "error");
  }
});

loadState().catch((error) => {
  showFlash(error.message, "error");
});
