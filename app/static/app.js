const activeFilters = {
    departure_time_filters: new Set(),
    flight_attribute_filters: new Set(),
    airline_filters: new Set(),
};

const selectedTagsElement = document.querySelector("#selected-tags");
const searchSummaryElement = document.querySelector("#search-summary");
const clearFiltersButton = document.querySelector("#clear-filters");
const searchForm = document.querySelector("#search-form");
const resultsListElement = document.querySelector("#results-list");
const historyListElement = document.querySelector("#history-list");
const monitorForm = document.querySelector("#monitor-form");
const monitorListElement = document.querySelector("#monitor-list");
const monitorDetailElement = document.querySelector("#monitor-detail");
const monitorFormResetButton = document.querySelector("#monitor-form-reset");
const dashboardActionsRoot = document.body;
const filterChipSelector = "[data-filter-group-name][data-filter-value]";
const filterGroupNames = Object.keys(activeFilters);

function focusAndScroll(selector) {
    const element = document.querySelector(selector);
    if (!element) {
        return;
    }

    element.scrollIntoView({ behavior: "smooth", block: "start" });
    const focusTarget = element.querySelector("input, button, [tabindex]");
    if (focusTarget instanceof HTMLElement) {
        focusTarget.focus();
    }
}

function playMonitorHitTone() {
    const AudioContextConstructor = window.AudioContext || window.webkitAudioContext;
    if (!AudioContextConstructor) {
        return;
    }

    const audioContext = new AudioContextConstructor();
    const oscillator = audioContext.createOscillator();
    const gain = audioContext.createGain();
    oscillator.type = "sine";
    oscillator.frequency.value = 880;
    gain.gain.value = 0.03;
    oscillator.connect(gain);
    gain.connect(audioContext.destination);
    oscillator.start();
    oscillator.stop(audioContext.currentTime + 0.18);
    oscillator.addEventListener("ended", () => {
        audioContext.close();
    });
}

function getActiveFilterCount() {
    return Object.values(activeFilters).reduce((total, valueSet) => total + valueSet.size, 0);
}

function createSelectedTag(groupName, value) {
    const tag = document.createElement("span");
    tag.className = "selected-tag";

    const label = document.createElement("span");
    label.textContent = value;

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.textContent = "移除";
    removeButton.setAttribute("aria-label", `移除 ${value} 筛选条件`);
    removeButton.addEventListener("click", () => toggleFilterValue(groupName, value));

    tag.append(label, removeButton);
    return tag;
}

function renderSelectedTags() {
    if (!selectedTagsElement || !searchSummaryElement) {
        return;
    }

    selectedTagsElement.replaceChildren();

    const fragment = document.createDocumentFragment();
    let count = 0;

    Object.entries(activeFilters).forEach(([groupName, values]) => {
        values.forEach((value) => {
            fragment.appendChild(createSelectedTag(groupName, value));
            count += 1;
        });
    });

    if (count === 0) {
        const emptyState = document.createElement("span");
        emptyState.className = "empty-state-tag";
        emptyState.textContent = "暂未选择筛选条件。";
        selectedTagsElement.appendChild(emptyState);
        searchSummaryElement.textContent = "可以开始搜索，当前没有选择筛选条件。";
        return;
    }

    selectedTagsElement.appendChild(fragment);
    searchSummaryElement.textContent = `可以开始搜索，已选择 ${count} 个筛选条件。`;
}

function syncChipState(groupName, value) {
    const selector = `[data-filter-group-name="${groupName}"][data-filter-value="${value}"]`;
    document.querySelectorAll(selector).forEach((chip) => {
        chip.classList.toggle("is-active", activeFilters[groupName].has(value));
        chip.setAttribute("aria-pressed", activeFilters[groupName].has(value) ? "true" : "false");
    });
}

function toggleFilterValue(groupName, value) {
    const groupSet = activeFilters[groupName];
    if (!groupSet) {
        return;
    }

    if (groupSet.has(value)) {
        groupSet.delete(value);
    } else {
        groupSet.add(value);
    }

    syncChipState(groupName, value);
    renderSelectedTags();
}

function replaceFilters(nextFilters = {}) {
    filterGroupNames.forEach((groupName) => {
        const nextValues = new Set(nextFilters[groupName] || []);
        const currentValues = Array.from(activeFilters[groupName]);

        currentValues.forEach((value) => {
            if (!nextValues.has(value)) {
                activeFilters[groupName].delete(value);
                syncChipState(groupName, value);
            }
        });

        nextValues.forEach((value) => {
            if (!activeFilters[groupName].has(value)) {
                activeFilters[groupName].add(value);
            }
            syncChipState(groupName, value);
        });
    });

    renderSelectedTags();
}

function toggleFilterGroup(groupName) {
    const toggleButton = document.querySelector(`[data-filter-toggle="${groupName}"]`);
    const optionsBlock = document.querySelector(`[data-filter-group="${groupName}"]`);

    if (!toggleButton || !optionsBlock) {
        return;
    }

    const isExpanded = toggleButton.getAttribute("aria-expanded") === "true";
    toggleButton.setAttribute("aria-expanded", isExpanded ? "false" : "true");
    optionsBlock.hidden = isExpanded;
    optionsBlock.classList.toggle("is-collapsed", isExpanded);
}

function clearFilters() {
    filterGroupNames.forEach((groupName) => {
        Array.from(activeFilters[groupName]).forEach((value) => {
            activeFilters[groupName].delete(value);
            syncChipState(groupName, value);
        });
    });

    renderSelectedTags();
}

function getSearchPayload() {
    if (!searchForm) {
        return null;
    }

    const formData = new FormData(searchForm);
    const maxPriceValue = formData.get("max_price");
    const payload = {
        origin_city: String(formData.get("origin_city") || "").trim(),
        destination_city: String(formData.get("destination_city") || "").trim(),
        departure_date: String(formData.get("departure_date") || ""),
        departure_time_filters: Array.from(activeFilters.departure_time_filters),
        flight_attribute_filters: Array.from(activeFilters.flight_attribute_filters),
        airline_filters: Array.from(activeFilters.airline_filters),
    };

    if (maxPriceValue !== null && String(maxPriceValue).trim() !== "") {
        payload.max_price = Number(maxPriceValue);
    }

    return payload;
}

function createPlaceholderResultCard(title, description, priceLabel = "--", extraClass = "") {
    const article = document.createElement("article");
    article.className = `result-card ${extraClass}`.trim();

    const content = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = title;
    const body = document.createElement("p");
    body.textContent = description;
    content.append(heading, body);

    const price = document.createElement("span");
    price.className = "result-price";
    price.textContent = priceLabel;

    article.append(content, price);
    return article;
}

function renderResults(response) {
    if (!resultsListElement || !searchSummaryElement) {
        return;
    }

    resultsListElement.replaceChildren();

    if (!response || !Array.isArray(response.flights) || response.flights.length === 0) {
        resultsListElement.appendChild(
            createPlaceholderResultCard(
                "没有找到符合条件的机票",
                "可以调整航线、日期或筛选条件后再试一次。",
                response && response.lowest_price ? `¥${response.lowest_price}` : "--",
                "placeholder-card"
            )
        );
        searchSummaryElement.textContent = "搜索完成，但没有找到符合条件的机票。";
        return;
    }

    const fragment = document.createDocumentFragment();
    response.flights.forEach((flight) => {
        const article = document.createElement("article");
        article.className = "result-card";

        const content = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = `${flight.airline} ${flight.flight_no}`;
        const body = document.createElement("p");
        body.textContent = `${flight.origin_city} → ${flight.destination_city} · ${flight.departure_time} - ${flight.arrival_time} · ${flight.stop_info}`;
        content.append(heading, body);

        const price = document.createElement("span");
        price.className = "result-price";
        price.textContent = `¥${flight.price}`;

        article.append(content, price);
        fragment.appendChild(article);
    });

    resultsListElement.appendChild(fragment);
    const filterCount = getActiveFilterCount();
    const lowestPriceText = response.lowest_price === null || response.lowest_price === undefined
        ? "--"
        : `¥${response.lowest_price}`;
    searchSummaryElement.textContent = `找到 ${response.flights.length} 个航班，最低价 ${lowestPriceText}${filterCount > 0 ? `，已应用 ${filterCount} 个筛选条件` : ""}。`;
}

function createHistoryRow(record) {
    const article = document.createElement("article");
    article.className = "history-row";
    article.dataset.historyId = String(record.id);

    const content = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = `${record.origin_city} → ${record.destination_city}`;
    const maxPriceText = record.max_price === null || record.max_price === undefined ? "不限价格" : `最高 ¥${record.max_price}`;
    const body = document.createElement("p");
    body.textContent = `${record.departure_date} · ${maxPriceText}`;
    content.append(heading, body);

    const actions = document.createElement("div");
    actions.className = "history-actions";

    ["rerun", "edit"].forEach((action) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.historyAction = action;
        button.dataset.historyId = String(record.id);
        button.textContent = action === "rerun" ? "重新搜索" : "编辑";
        actions.appendChild(button);
    });

    article.append(content, actions);
    return article;
}

function getMonitorPayload() {
    if (!monitorForm) {
        return null;
    }

    const formData = new FormData(monitorForm);
    return {
        origin_city: String(formData.get("origin_city") || "").trim(),
        destination_city: String(formData.get("destination_city") || "").trim(),
        departure_date: String(formData.get("departure_date") || ""),
        target_price: Number(formData.get("target_price") || 0),
        check_interval_minutes: Number(formData.get("check_interval_minutes") || 30),
        departure_time_filters: Array.from(activeFilters.departure_time_filters),
        flight_attribute_filters: Array.from(activeFilters.flight_attribute_filters),
        airline_filters: Array.from(activeFilters.airline_filters),
    };
}

function resetMonitorForm() {
    if (!monitorForm) {
        return;
    }

    monitorForm.reset();
    if (monitorForm.elements.check_interval_minutes) {
        monitorForm.elements.check_interval_minutes.value = "30";
    }
    delete monitorForm.dataset.monitorId;
}

function fillMonitorForm(record) {
    if (!monitorForm || !record) {
        return;
    }

    monitorForm.elements.origin_city.value = record.origin_city || "";
    monitorForm.elements.destination_city.value = record.destination_city || "";
    monitorForm.elements.departure_date.value = record.departure_date || "";
    monitorForm.elements.target_price.value = record.target_price ?? "";
    monitorForm.elements.check_interval_minutes.value = record.check_interval_minutes ?? 30;
    monitorForm.dataset.monitorId = String(record.id || "");
    replaceFilters({
        departure_time_filters: record.departure_time_filters || [],
        flight_attribute_filters: record.flight_attribute_filters || [],
        airline_filters: record.airline_filters || [],
    });
}

function setMonitorDetail(record) {
    if (!monitorDetailElement) {
        return;
    }

    if (!record) {
        const headingWrapper = document.createElement("div");
        headingWrapper.className = "panel-heading compact";

        const headingContent = document.createElement("div");
        const kicker = document.createElement("p");
        kicker.className = "panel-kicker";
        kicker.textContent = "当前选择";
        const heading = document.createElement("h3");
        heading.textContent = "监控详情";
        headingContent.append(kicker, heading);
        headingWrapper.appendChild(headingContent);

        const detailCopy = document.createElement("div");
        detailCopy.className = "monitor-detail-copy";

        const descriptionElement = document.createElement("p");
        descriptionElement.textContent = "选择一个监控任务，可查看最近检查和命中记录。";
        detailCopy.appendChild(descriptionElement);

        monitorDetailElement.replaceChildren(headingWrapper, detailCopy);
        return;
    }

    renderMonitorDetail(record, []);
}

function formatMonitorHitTime(isoString) {
    if (!isoString) {
        return "";
    }

    const parsedDate = new Date(isoString);
    if (Number.isNaN(parsedDate.getTime())) {
        return isoString;
    }

    return parsedDate.toLocaleString();
}

function buildFlightLinkUrl(flight) {
    return flight.deeplink_url || flight.fallback_search_url || "";
}

function createMonitorFlightButton(flight) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "text-action";
    button.textContent = `${flight.airline || "未知航司"} ${flight.flight_no || ""} · ¥${flight.price ?? "--"}`.trim();

    const targetUrl = buildFlightLinkUrl(flight);
    if (!targetUrl) {
        button.disabled = true;
        return button;
    }

    button.addEventListener("click", () => {
        window.open(targetUrl, "_blank", "noopener,noreferrer");
    });
    return button;
}

function createMonitorHitCard(hit) {
    const article = document.createElement("article");
    article.className = "monitor-hit-card";
    article.dataset.monitorHitId = String(hit.id);
    article.tabIndex = -1;

    const content = document.createElement("div");
    const heading = document.createElement("h4");
    heading.textContent = `命中 ¥${hit.lowest_price}`;
    const body = document.createElement("p");
    body.textContent = `命中时间：${formatMonitorHitTime(hit.hit_at)}`;
    content.append(heading, body);

    const flightsContainer = document.createElement("div");
    flightsContainer.className = "monitor-detail-actions";

    const flights = Array.isArray(hit.search_snapshot_json) ? hit.search_snapshot_json : [];
    if (flights.length === 0) {
        const emptyState = document.createElement("p");
        emptyState.textContent = "这次命中没有保存航班快照。";
        flightsContainer.appendChild(emptyState);
    } else {
        flights.forEach((flight) => {
            flightsContainer.appendChild(createMonitorFlightButton(flight));
        });
    }

    article.append(content, flightsContainer);
    return article;
}

function focusMonitorHit(monitorHitId) {
    if (!monitorDetailElement || !monitorHitId) {
        return;
    }

    const hitCard = monitorDetailElement.querySelector(`[data-monitor-hit-id="${monitorHitId}"]`);
    if (!hitCard) {
        return;
    }

    monitorDetailElement.querySelectorAll("[data-monitor-hit-focused]").forEach((card) => {
        delete card.dataset.monitorHitFocused;
        card.classList.remove("is-highlighted");
    });

    hitCard.dataset.monitorHitFocused = "true";
    hitCard.setAttribute("data-monitor-hit-tone", "played");
    hitCard.classList.add("is-highlighted");
    hitCard.scrollIntoView({ behavior: "smooth", block: "center" });
    hitCard.focus({ preventScroll: true });
    playMonitorHitTone();
}

function renderMonitorDetail(task, hits, highlightedHitId = null) {
    if (!monitorDetailElement || !task) {
        return;
    }

    const title = `${task.origin_city} → ${task.destination_city}`;
    const description = `${task.departure_date} · 目标 ¥${task.target_price} · 每 ${task.check_interval_minutes} 分钟检查 · ${task.enabled ? "运行中" : "已暂停"}`;
    const toggleLabel = task.enabled ? "暂停" : "恢复";
    const monitorId = String(task.id || "");

    const headingWrapper = document.createElement("div");
    headingWrapper.className = "panel-heading compact";

    const headingContent = document.createElement("div");
    const kicker = document.createElement("p");
    kicker.className = "panel-kicker";
    kicker.textContent = "当前选择";
    const heading = document.createElement("h3");
    heading.textContent = title;
    headingContent.append(kicker, heading);
    headingWrapper.appendChild(headingContent);

    const detailCopy = document.createElement("div");
    detailCopy.className = "monitor-detail-copy";

    const descriptionElement = document.createElement("p");
    descriptionElement.textContent = description;

    const actions = document.createElement("div");
    actions.className = "monitor-detail-actions";

    const editButton = document.createElement("button");
    editButton.type = "button";
    editButton.className = "text-action";
    editButton.dataset.monitorAction = "edit";
    editButton.dataset.monitorId = monitorId;
    editButton.textContent = "编辑";

    const toggleButton = document.createElement("button");
    toggleButton.type = "button";
    toggleButton.className = "text-action";
    toggleButton.dataset.monitorAction = "toggle";
    toggleButton.dataset.monitorId = monitorId;
    toggleButton.textContent = toggleLabel;

    actions.append(editButton, toggleButton);
    detailCopy.append(descriptionElement, actions);

    const hitsHeading = document.createElement("h4");
    hitsHeading.textContent = "命中记录";

    const hitList = document.createElement("div");
    hitList.id = "monitor-hit-list";

    if (!Array.isArray(hits) || hits.length === 0) {
        const emptyState = document.createElement("p");
        emptyState.textContent = "这个监控还没有命中记录。";
        hitList.appendChild(emptyState);
    } else {
        hits.forEach((hit) => {
            const hitCard = createMonitorHitCard(hit);
            if (highlightedHitId && String(hit.id) === String(highlightedHitId)) {
                hitCard.classList.add("is-highlighted");
            }
            hitList.appendChild(hitCard);
        });
    }

    monitorDetailElement.replaceChildren(headingWrapper, detailCopy, hitsHeading, hitList);
}

async function loadMonitorDetail(monitorId, monitorHitId = null) {
    if (!monitorId) {
        setMonitorDetail(null);
        return;
    }

    try {
        const [task, hits] = await Promise.all([
            requestJson(`/api/monitors/${monitorId}`),
            requestJson(`/api/monitors/${monitorId}/hits`),
        ]);
        renderMonitorDetail(task, hits, monitorHitId);
        focusMonitorHit(monitorHitId);
    } catch (error) {
        setMonitorDetail(null);
        searchSummaryElement.textContent = `监控详情加载失败。${error.message}`;
    }
}

function createMonitorRow(record) {
    const article = document.createElement("article");
    article.className = "monitor-row";
    article.dataset.monitorId = String(record.id);
    article.dataset.monitorEnabled = record.enabled ? "true" : "false";

    const content = document.createElement("div");
    const heading = document.createElement("h3");
    heading.textContent = `${record.origin_city} → ${record.destination_city}`;
    const body = document.createElement("p");
    body.textContent = `${record.departure_date} · 目标 ¥${record.target_price} · 每 ${record.check_interval_minutes} 分钟检查`;
    content.append(heading, body);

    const actions = document.createElement("div");
    actions.className = "history-actions monitor-actions";

    [
        { action: "edit", label: "编辑" },
        { action: "toggle", label: record.enabled ? "暂停" : "恢复" },
    ].forEach(({ action, label }) => {
        const button = document.createElement("button");
        button.type = "button";
        button.dataset.monitorAction = action;
        button.dataset.monitorId = String(record.id);
        button.textContent = label;
        actions.appendChild(button);
    });

    article.append(content, actions);
    return article;
}

function renderMonitorList(monitors) {
    if (!monitorListElement) {
        return;
    }

    monitorListElement.replaceChildren();

    if (!Array.isArray(monitors) || monitors.length === 0) {
        const article = document.createElement("article");
        article.className = "monitor-row empty-history";

        const content = document.createElement("div");
        const heading = document.createElement("h3");
        heading.textContent = "还没有监控任务";
        const body = document.createElement("p");
        body.textContent = "保存一个目标价，程序会在后台定时检查。";
        content.append(heading, body);
        article.appendChild(content);

        monitorListElement.appendChild(article);
        setMonitorDetail(null);
        return;
    }

    const fragment = document.createDocumentFragment();
    monitors.forEach((record) => {
        fragment.appendChild(createMonitorRow(record));
    });
    monitorListElement.appendChild(fragment);
}

async function loadMonitorList() {
    if (!monitorListElement) {
        return;
    }

    try {
        const monitors = await requestJson("/api/monitors");
        renderMonitorList(monitors);
    } catch (error) {
        renderMonitorList([]);
        setMonitorDetail(null);
    }
}

function updateMonitorListRecord(record) {
    if (!monitorListElement || !record || record.id === null || record.id === undefined) {
        return;
    }

    monitorListElement.querySelector(".empty-history")?.remove();
    const nextRow = createMonitorRow(record);
    const existingRow = monitorListElement.querySelector(`[data-monitor-id="${record.id}"]`);

    if (existingRow) {
        existingRow.replaceWith(nextRow);
    } else {
        monitorListElement.prepend(nextRow);
    }

    loadMonitorDetail(record.id);
}

function upsertHistoryRecord(record) {
    if (!historyListElement || !record || record.id === null || record.id === undefined) {
        return;
    }

    historyListElement.querySelector(".empty-history")?.remove();
    const nextRow = createHistoryRow(record);
    const existingRow = historyListElement.querySelector(`[data-history-id="${record.id}"]`);

    if (existingRow) {
        existingRow.replaceWith(nextRow);
        return;
    }

    historyListElement.prepend(nextRow);
}

function fillSearchForm(record) {
    if (!searchForm) {
        return;
    }

    searchForm.elements.origin_city.value = record.origin_city || "";
    searchForm.elements.destination_city.value = record.destination_city || "";
    searchForm.elements.departure_date.value = record.departure_date || "";
    searchForm.elements.max_price.value = record.max_price ?? "";
    replaceFilters({
        departure_time_filters: record.departure_time_filters || [],
        flight_attribute_filters: record.flight_attribute_filters || [],
        airline_filters: record.airline_filters || [],
    });
}

async function requestJson(url, options = {}) {
    const response = await fetch(url, {
        headers: {
            "Content-Type": "application/json",
            ...(options.headers || {}),
        },
        ...options,
    });

    const payload = await response.json().catch(() => null);
    if (!response.ok) {
        const message = payload && (payload.message || payload.detail) ? payload.message || payload.detail : "请求失败";
        throw new Error(message);
    }

    return payload;
}

async function runSearch(event) {
    event.preventDefault();

    const payload = getSearchPayload();
    if (!payload) {
        return;
    }

    searchSummaryElement.textContent = "正在搜索机票...";

    try {
        const response = await requestJson("/api/search", {
            method: "POST",
            body: JSON.stringify(payload),
        });
        renderResults(response);
        if (response.history_id !== null && response.history_id !== undefined) {
            upsertHistoryRecord({ id: response.history_id, ...payload });
        }
    } catch (error) {
        resultsListElement.replaceChildren(
            createPlaceholderResultCard("搜索失败", error.message, "--", "placeholder-card")
        );
        searchSummaryElement.textContent = `搜索失败。${error.message}`;
    }
}

async function handleHistoryAction(event) {
    const button = event.target.closest("[data-history-action][data-history-id]");
    if (!button) {
        return;
    }

    const { historyAction, historyId } = button.dataset;
    if (!historyAction || !historyId) {
        return;
    }

    try {
        if (historyAction === "edit") {
            const record = await requestJson(`/api/history/${historyId}`);
            fillSearchForm(record);
            searchSummaryElement.textContent = `已把历史记录 ${historyId} 填入搜索表单。`;
            return;
        }

        if (historyAction === "rerun") {
            searchSummaryElement.textContent = `正在重新搜索历史记录 ${historyId}...`;
            const response = await requestJson(`/api/history/${historyId}/rerun`, { method: "POST" });
            renderResults(response);
            const record = await requestJson(`/api/history/${response.history_id}`);
            upsertHistoryRecord(record);
        }
    } catch (error) {
        searchSummaryElement.textContent = `${historyAction === "edit" ? "编辑" : "重新搜索"}失败。${error.message}`;
    }
}

async function handleMonitorSubmit(event) {
    event.preventDefault();

    const payload = getMonitorPayload();
    if (!payload) {
        return;
    }

    const existingId = monitorForm?.dataset.monitorId;
    const url = existingId ? `/api/monitors/${existingId}` : "/api/monitors";
    const method = existingId ? "PUT" : "POST";

    try {
        const record = await requestJson(url, {
            method,
            body: JSON.stringify(payload),
        });
        updateMonitorListRecord(record);
        fillMonitorForm(record);
        searchSummaryElement.textContent = `已${existingId ? "更新" : "保存"} ${record.origin_city} → ${record.destination_city} 的监控任务。`;
    } catch (error) {
        searchSummaryElement.textContent = `监控保存失败。${error.message}`;
    }
}

async function handleMonitorAction(event) {
    const button = event.target.closest("[data-monitor-action]");
    if (!button) {
        return;
    }

    const { monitorAction, monitorId } = button.dataset;
    if (!monitorAction || !monitorId) {
        if (monitorAction === "edit" && !monitorId) {
            searchSummaryElement.textContent = "请先选择一个已保存的监控任务。";
        }
        return;
    }

    try {
        const record = await requestJson(`/api/monitors/${monitorId}`);

        if (monitorAction === "edit") {
            fillMonitorForm(record);
            await loadMonitorDetail(monitorId);
            searchSummaryElement.textContent = `已把监控任务 ${monitorId} 填入表单。`;
            return;
        }

        if (monitorAction === "toggle") {
            const updatedRecord = await requestJson(`/api/monitors/${monitorId}`, {
                method: "PUT",
                body: JSON.stringify({
                    origin_city: record.origin_city,
                    destination_city: record.destination_city,
                    departure_date: record.departure_date,
                    target_price: record.target_price,
                    check_interval_minutes: record.check_interval_minutes,
                    departure_time_filters: record.departure_time_filters || [],
                    flight_attribute_filters: record.flight_attribute_filters || [],
                    airline_filters: record.airline_filters || [],
                    enabled: !record.enabled,
                }),
            });
            updateMonitorListRecord(updatedRecord);
            searchSummaryElement.textContent = `监控任务 ${monitorId} 已${updatedRecord.enabled ? "恢复" : "暂停"}。`;
        }
    } catch (error) {
        searchSummaryElement.textContent = `监控操作失败。${error.message}`;
    }
}

async function handleDashboardAction(event) {
    const button = event.target.closest("[data-dashboard-action]");
    if (!button) {
        return;
    }

    const action = button.dataset.dashboardAction;
    if (!action) {
        return;
    }

    if (action === "relogin") {
        searchSummaryElement.textContent = "正在打开携程登录...";
        const payload = await requestJson("/api/session/relogin", { method: "POST" });
        searchSummaryElement.textContent = payload.status === "login_started"
            ? "已打开携程登录窗口，请完成登录后返回这里。"
            : "当前缺少登录页面配置，请先检查环境设置。";
        return;
    }

    if (action === "search") {
        focusAndScroll("#search-form");
        return;
    }

    if (action === "create-monitor") {
        focusAndScroll("#monitor-form");
        return;
    }

    if (action === "view-hit") {
        const monitorTaskId = button.dataset.monitorTaskId;
        const monitorHitId = button.dataset.monitorHitId;
        if (monitorTaskId) {
            await loadMonitorDetail(monitorTaskId, monitorHitId || null);
            if (!monitorHitId) {
                focusAndScroll("#monitor-detail");
            }
        }
    }
}

document.querySelectorAll("[data-filter-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
        toggleFilterGroup(button.dataset.filterToggle);
    });
});


document.querySelectorAll(filterChipSelector).forEach((chip) => {
    chip.setAttribute("aria-pressed", "false");
    chip.addEventListener("click", () => {
        toggleFilterValue(chip.dataset.filterGroupName, chip.dataset.filterValue);
    });
});

if (clearFiltersButton) {
    clearFiltersButton.addEventListener("click", clearFilters);
}

if (searchForm) {
    searchForm.addEventListener("submit", runSearch);
}

if (historyListElement) {
    historyListElement.addEventListener("click", handleHistoryAction);
}

if (monitorForm) {
    monitorForm.addEventListener("submit", handleMonitorSubmit);
}

if (monitorFormResetButton) {
    monitorFormResetButton.addEventListener("click", () => {
        resetMonitorForm();
        setMonitorDetail(null);
        searchSummaryElement.textContent = "已清空监控草稿。";
    });
}

if (monitorListElement) {
    monitorListElement.addEventListener("click", handleMonitorAction);
}

if (monitorDetailElement) {
    monitorDetailElement.addEventListener("click", handleMonitorAction);
}

if (dashboardActionsRoot) {
    dashboardActionsRoot.addEventListener("click", (event) => {
        handleDashboardAction(event).catch((error) => {
            searchSummaryElement.textContent = `操作失败。${error.message}`;
        });
    });
}

renderSelectedTags();
setMonitorDetail(null);
loadMonitorList();

const params = new URLSearchParams(window.location.search);
const initialMonitorTaskId = params.get("monitor_task_id");
const initialMonitorHitId = params.get("monitor_hit_id");
if (initialMonitorTaskId) {
    loadMonitorDetail(initialMonitorTaskId, initialMonitorHitId);
}
