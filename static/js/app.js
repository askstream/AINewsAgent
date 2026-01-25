// Инициализация после загрузки DOM
document.addEventListener('DOMContentLoaded', function() {
    // Инициализация переменных
    let currentTaskId = null;
    let currentSearchHistoryId = null;
    let statusInterval = null;
    let currentHistoryPage = 1;
    let currentHistoryData = null;
    let expandedArticleId = null;
    let expandedArticlePrefix = null;

    // Получение элементов DOM
    const form = document.getElementById('processingForm');
    const startBtn = document.getElementById('startBtn');
    const emptyState = document.getElementById('emptyState');
    const stepsContainer = document.getElementById('stepsContainer');
    const statisticsRow = document.getElementById('statisticsRow');
    const successAlert = document.getElementById('successAlert');
    const errorAlert = document.getElementById('errorAlert');
    const confirmClearBtn = document.getElementById('confirmClearBtn');

    if (!form || !startBtn || !confirmClearBtn) {
        console.error('Не найдены необходимые элементы DOM');
        return;
    }

    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();
            const rssFeeds = document.getElementById('rss_feeds').value;
            const criteria = document.getElementById('criteria').value;
            const llmModel = document.getElementById('llm_model').value.trim();
            const llmTemperature = parseFloat(document.getElementById('llm_temperature').value);
            const similarityThreshold = parseFloat(document.getElementById('similarity_threshold').value);

            if (!rssFeeds.trim() || !criteria.trim()) {
                alert('Заполните обязательные поля: RSS каналы и критерий отбора');
                return;
            }

            // Валидация параметров
            if (isNaN(llmTemperature) || llmTemperature < 0 || llmTemperature > 2) {
                alert('Temperature должен быть числом от 0.0 до 2.0');
                return;
            }

            if (isNaN(similarityThreshold) || similarityThreshold < 0 || similarityThreshold > 1) {
                alert('Порог схожести должен быть числом от 0.0 до 1.0');
                return;
            }

            startBtn.disabled = true;
            startBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Поиск...';

            try {
                const response = await fetch('/api/start', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        rss_feeds: rssFeeds,
                        criteria: criteria,
                        llm_model: llmModel,
                        llm_temperature: llmTemperature,
                        similarity_threshold: similarityThreshold
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    currentTaskId = data.task_id;
                    currentSearchHistoryId = null; // Сброс при новом поиске
                    emptyState.style.display = 'none';
                    stepsContainer.style.display = 'block';
                    initializeSteps();
                    startStatusPolling();
                    // Скрываем кнопку удаления до завершения поиска
                    document.getElementById('deleteCurrentSearchBtn').style.display = 'none';
                } else {
                    showError(data.error || 'Ошибка при запуске обработки');
                }
            } catch (error) {
                showError('Ошибка при отправке запроса: ' + error.message);
            } finally {
                startBtn.disabled = false;
                startBtn.innerHTML = '<i class="bi bi-search"></i> Поиск';
            }
        });
    }

    function initializeSteps() {
        stepsContainer.innerHTML = '';
        const steps = [
            'Сбор новостей из RSS каналов',
            'Дедупликация статей',
            'Классификация по релевантности'
        ];

        steps.forEach((stepName, index) => {
            const stepCard = document.createElement('div');
            stepCard.className = 'card step-card';
            stepCard.id = `step-${index}`;
            stepCard.innerHTML = `
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <h6 class="mb-0">
                            <i class="bi bi-circle" id="icon-${index}"></i> ${stepName}
                        </h6>
                        <span class="badge bg-secondary" id="status-${index}">Ожидание</span>
                    </div>
                    <div class="progress mb-2" style="height: 8px;">
                        <div class="progress-bar" id="progress-${index}" role="progressbar" 
                            style="width: 0%" aria-valuenow="0" aria-valuemin="0" aria-valuemax="100"></div>
                    </div>
                    <small class="text-muted" id="message-${index}"></small>
                </div>
            `;
            stepsContainer.appendChild(stepCard);
        });
    }

    function startStatusPolling() {
        if (statusInterval) {
            clearInterval(statusInterval);
        }

        statusInterval = setInterval(async () => {
            if (!currentTaskId) return;

            try {
                const response = await fetch(`/api/status/${currentTaskId}`);
                const status = await response.json();

                updateProgress(status);

                if (status.status === 'completed' || status.status === 'error') {
                    clearInterval(statusInterval);
                    startBtn.disabled = false;
                    startBtn.innerHTML = '<i class="bi bi-search"></i> Поиск';

                    if (status.status === 'completed') {
                        showSuccess();
                        showStatistics(status.statistics);
                        // Сохраняем ID истории запроса и показываем кнопку удаления
                        if (status.search_history_id) {
                            currentSearchHistoryId = status.search_history_id;
                            document.getElementById('deleteCurrentSearchBtn').style.display = 'block';
                        }
                        // Обновляем новости для текущего запроса
                        loadNews();
                    } else {
                        showError(status.error_message || 'Произошла ошибка при обработке');
                    }
                }
            } catch (error) {
                console.error('Ошибка при получении статуса:', error);
            }
        }, 1000);
    }

    function updateProgress(status) {
        status.steps.forEach((step, index) => {
            const stepCard = document.getElementById(`step-${index}`);
            const icon = document.getElementById(`icon-${index}`);
            const statusBadge = document.getElementById(`status-${index}`);
            const progressBar = document.getElementById(`progress-${index}`);
            const message = document.getElementById(`message-${index}`);

            // Обновление класса карточки
            stepCard.className = 'card step-card';
            if (step.status === 'running') {
                stepCard.classList.add('active');
                icon.className = 'bi bi-arrow-repeat pulse';
                statusBadge.className = 'badge bg-primary';
                statusBadge.textContent = 'Выполняется';
            } else if (step.status === 'completed') {
                stepCard.classList.add('completed');
                icon.className = 'bi bi-check-circle-fill text-success';
                statusBadge.className = 'badge bg-success';
                statusBadge.textContent = 'Завершено';
            } else if (step.status === 'error') {
                stepCard.classList.add('error');
                icon.className = 'bi bi-x-circle-fill text-danger';
                statusBadge.className = 'badge bg-danger';
                statusBadge.textContent = 'Ошибка';
            } else {
                icon.className = 'bi bi-circle';
                statusBadge.className = 'badge bg-secondary';
                statusBadge.textContent = 'Ожидание';
            }

            // Обновление прогресс-бара
            progressBar.style.width = step.progress + '%';
            progressBar.setAttribute('aria-valuenow', step.progress);
            progressBar.textContent = step.progress + '%';

            // Обновление сообщения
            message.textContent = step.message || '';
        });
    }

    function showSuccess() {
        successAlert.style.display = 'block';
        successAlert.classList.add('show');
        setTimeout(() => {
            successAlert.classList.remove('show');
            setTimeout(() => {
                successAlert.style.display = 'none';
            }, 300);
        }, 5000);
    }

    function showError(message) {
        document.getElementById('errorMessage').textContent = message;
        errorAlert.style.display = 'block';
        errorAlert.classList.add('show');
    }

    function showStatistics(stats) {
        if (!stats || Object.keys(stats).length === 0) return;

        statisticsRow.style.display = 'block';
        const content = document.getElementById('statisticsContent');

        if (stats.message) {
            content.innerHTML = `<div class="col-12"><p class="text-muted">${stats.message}</p></div>`;
        } else {
            content.innerHTML = `
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-primary">${stats.total || 0}</h3>
                        <p class="mb-0 text-muted">Всего статей</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-success">${stats.relevant || 0}</h3>
                        <p class="mb-0 text-muted">Релевантных</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-warning">${stats.duplicates || 0}</h3>
                        <p class="mb-0 text-muted">Дубликатов</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-info">${stats.unique_non_relevant || 0}</h3>
                        <p class="mb-0 text-muted">Уникальных нерелевантных</p>
                    </div>
                </div>
            `;
        }
    }

    // Обработчик очистки базы данных
    confirmClearBtn.addEventListener('click', async () => {
        confirmClearBtn.disabled = true;
        confirmClearBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Очистка...';

        try {
            const response = await fetch('/api/clear-db', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                }
            });

            let data;
            try {
                data = await response.json();
            } catch (jsonError) {
                // Если ответ не JSON, значит сервер вернул HTML (ошибка)
                const text = await response.text();
                console.error('Ошибка парсинга JSON:', text);
                showError('Ошибка сервера: получен неверный формат ответа');
                return;
            }

            if (response.ok && data.success) {
                const modalElement = document.getElementById('clearDbModal');
                const modal = bootstrap.Modal.getInstance(modalElement);
                if (modal) {
                    modal.hide();
                }
                showSuccessMessage(data.message || 'База данных успешно очищена');

                // Сброс прогресса
                emptyState.style.display = 'block';
                stepsContainer.style.display = 'none';
                statisticsRow.style.display = 'none';
                currentTaskId = null;
                if (statusInterval) {
                    clearInterval(statusInterval);
                }
            } else {
                showError(data.error || 'Ошибка при очистке базы данных');
            }
        } catch (error) {
            showError('Ошибка при отправке запроса: ' + error.message);
        } finally {
            confirmClearBtn.disabled = false;
            confirmClearBtn.innerHTML = '<i class="bi bi-trash"></i> Да, очистить базу';
        }
    });

    function showSuccessMessage(message) {
        successAlert.querySelector('strong').innerHTML = `<i class="bi bi-check-circle"></i> ${message}`;
        successAlert.style.display = 'block';
        successAlert.classList.add('show');
        setTimeout(() => {
            successAlert.classList.remove('show');
            setTimeout(() => {
                successAlert.style.display = 'none';
            }, 300);
        }, 5000);
    }

    // Загрузка новостей (для текущего запроса или всех)
    async function loadNews() {
        const tbody = document.getElementById('newsTableBody');
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4"><span class="spinner-border spinner-border-sm"></span> Загрузка...</td></tr>';

        try {
            let url = '/api/results';
            if (currentSearchHistoryId) {
                url += `?search_history_id=${currentSearchHistoryId}`;
            }
            const response = await fetch(url);
            const data = await response.json();

            if (response.ok && data.articles) {
                displayNews(data.articles);
            } else {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger py-4">Ошибка при загрузке новостей</td></tr>';
            }
        } catch (error) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger py-4">Ошибка: ' + error.message + '</td></tr>';
        }
    }

    function displayNews(articles) {
        const tbody = document.getElementById('newsTableBody');

        if (articles.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">Новостей пока нет</td></tr>';
            return;
        }

        tbody.innerHTML = '';

        articles.forEach(article => {
            // Основная строка
            const row = document.createElement('tr');
            row.className = 'news-article-group news-main-row';
            if (article.is_relevant) {
                row.classList.add('news-relevant', 'news-row-relevant');
            }

            // Форматирование даты
            let dateStr = 'Не указана';
            if (article.published_at) {
                const date = new Date(article.published_at);
                dateStr = date.toLocaleDateString('ru-RU', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            }

            // Форматирование релевантности
            const relevanceScore = article.relevance_score !== null ? (article.relevance_score * 100).toFixed(0) : '—';
            const relevanceBadgeClass = article.is_relevant ? 'bg-success' : 'bg-secondary';
            const relevanceText = article.is_relevant ? 'Релевантно' : 'Не релевантно';

            row.innerHTML = `
                <td class="align-middle">
                    <small class="text-muted">${article.id}</small>
                </td>
                <td class="align-middle">
                    <small class="news-meta">${escapeHtml(article.source)}</small>
                </td>
                <td class="align-middle">
                    <small class="news-meta">${dateStr}</small>
                </td>
                <td class="align-middle">
                    <div class="news-title">${escapeHtml(article.title)}</div>
                </td>
                <td class="align-middle">
                    <div>
                        <span class="badge ${relevanceBadgeClass} relevance-badge">${relevanceText}</span>
                        <small class="d-block text-muted mt-1">${relevanceScore}%</small>
                    </div>
                </td>
            `;
            tbody.appendChild(row);

            // Строка с содержанием (если есть)
            if (article.content && article.content.trim()) {
                const contentRow = document.createElement('tr');
                contentRow.className = 'news-article-group news-detail-row';
                contentRow.setAttribute('data-article-id', article.id);
                if (article.is_relevant) {
                    contentRow.classList.add('news-relevant', 'news-row-relevant');
                }
                // Санитизация HTML для безопасного отображения с сохранением разметки
                const sanitizedContent = DOMPurify.sanitize(article.content, {
                    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'code', 'pre', 'div', 'span'],
                    ALLOWED_ATTR: ['href', 'target', 'rel', 'class']
                });
                contentRow.innerHTML = `
                    <td colspan="5" class="py-2 px-3">
                        <div class="news-content-full news-content-collapsed" id="content-${article.id}">${sanitizedContent}</div>
                        <div class="mt-2">
                            <span class="news-expand-btn text-primary" onclick="toggleArticleContent(${article.id}, this)">
                                <i class="bi bi-chevron-down" id="icon-${article.id}"></i> <span id="text-${article.id}">Развернуть</span>
                            </span>
                        </div>
                    </td>
                `;
                tbody.appendChild(contentRow);
            }

            // Строка с причиной классификации (если есть)
            if (article.classification_reason && article.classification_reason.trim()) {
                const reasonRow = document.createElement('tr');
                reasonRow.className = 'news-article-group news-detail-row';
                if (article.is_relevant) {
                    reasonRow.classList.add('news-relevant', 'news-row-relevant');
                }
                reasonRow.innerHTML = `
                    <td colspan="5" class="py-2 px-3">
                        <small class="text-muted">
                            <i class="bi bi-info-circle"></i> <strong>Причина:</strong> ${escapeHtml(article.classification_reason)}
                        </small>
                    </td>
                `;
                tbody.appendChild(reasonRow);
            }
        });
    }

    function escapeHtml(text) {
        if (!text) return '';
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    // Загрузка статистики после поиска
    async function loadStatisticsFromApi() {
        const content = document.getElementById('statisticsContent');
        content.innerHTML = '<div class="col-12 text-center"><span class="spinner-border spinner-border-sm"></span> Загрузка...</div>';

        try {
            const response = await fetch('/api/statistics');
            const data = await response.json();

            if (response.ok) {
                statisticsRow.style.display = 'block';
                showStatistics({
                    total: data.total,
                    relevant: data.relevant,
                    duplicates: data.duplicates,
                    unique_non_relevant: data.unique_non_relevant
                });
            } else {
                content.innerHTML = '<div class="col-12 text-center text-danger">Ошибка при загрузке статистики</div>';
            }
        } catch (error) {
            content.innerHTML = '<div class="col-12 text-center text-danger">Ошибка: ' + error.message + '</div>';
        }
    }

    // Загрузка общей статистики
    async function loadGeneralStatistics() {
        const content = document.getElementById('generalStatsContent');
        content.innerHTML = '<div class="text-center text-muted py-3"><span class="spinner-border spinner-border-sm"></span> Загрузка...</div>';

        try {
            const response = await fetch('/api/statistics');
            const data = await response.json();

            if (response.ok) {
                displayGeneralStatistics(data);
            } else {
                content.innerHTML = '<div class="text-center text-danger py-3">Ошибка при загрузке статистики</div>';
            }
        } catch (error) {
            content.innerHTML = '<div class="text-center text-danger py-3">Ошибка: ' + error.message + '</div>';
        }
    }

    function displayGeneralStatistics(stats) {
        const content = document.getElementById('generalStatsContent');

        let sourcesHtml = '';
        if (stats.sources && stats.sources.length > 0) {
            sourcesHtml = '<div class="mt-3"><h6>Статистика по источникам:</h6><ul class="list-group">';
            stats.sources.forEach(source => {
                sourcesHtml += `<li class="list-group-item d-flex justify-content-between align-items-center">
                    ${escapeHtml(source.name)}
                    <span class="badge bg-primary rounded-pill">${source.count}</span>
                </li>`;
            });
            sourcesHtml += '</ul></div>';
        }

        let searchesHtml = '';
        if (stats.last_searches && stats.last_searches.length > 0) {
            searchesHtml = '<div class="mt-3"><h6>Последние поиски:</h6><ul class="list-group">';
            stats.last_searches.forEach(search => {
                const date = search.date ? new Date(search.date).toLocaleString('ru-RU') : 'Не указана';
                searchesHtml += `<li class="list-group-item d-flex justify-content-between align-items-center">
                    ${date}
                    <span class="badge bg-info rounded-pill">${search.count} статей</span>
                </li>`;
            });
            searchesHtml += '</ul></div>';
        }

        content.innerHTML = `
            <div class="row">
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-primary">${stats.total || 0}</h3>
                        <p class="mb-0 text-muted">Всего статей</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-success">${stats.relevant || 0}</h3>
                        <p class="mb-0 text-muted">Релевантных</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-warning">${stats.duplicates || 0}</h3>
                        <p class="mb-0 text-muted">Дубликатов</p>
                    </div>
                </div>
                <div class="col-md-3">
                    <div class="text-center p-3 bg-light rounded">
                        <h3 class="text-info">${stats.unique_non_relevant || 0}</h3>
                        <p class="mb-0 text-muted">Уникальных нерелевантных</p>
                    </div>
                </div>
            </div>
            ${sourcesHtml}
            ${searchesHtml}
        `;
    }

    // Автообновление новостей и статистики после завершения обработки
    const originalShowStatistics = showStatistics;
    showStatistics = function(stats) {
        originalShowStatistics(stats);
        setTimeout(() => {
            loadNews();
            loadGeneralStatistics();
        }, 1000);
    };

    // Удаление текущего запроса
    async function deleteCurrentSearch() {
        if (!currentSearchHistoryId) {
            alert('Нет активного запроса для удаления');
            return;
        }

        if (!confirm('Вы уверены, что хотите удалить данные текущего запроса? Это действие нельзя отменить!')) {
            return;
        }

        try {
            const response = await fetch(`/api/search-history/${currentSearchHistoryId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                alert(data.message || 'Запрос успешно удален');
                currentSearchHistoryId = null;
                document.getElementById('deleteCurrentSearchBtn').style.display = 'none';
                loadNews();
                loadGeneralStatistics();
                // Если открыта вкладка истории, обновляем её
                if (document.getElementById('history-tab').classList.contains('active')) {
                    loadSearchHistory();
                }
            } else {
                alert(data.error || 'Ошибка при удалении запроса');
            }
        } catch (error) {
            alert('Ошибка: ' + error.message);
        }
    }

    // Загрузка истории запросов
    async function loadSearchHistory(page = 1) {
        currentHistoryPage = page;
        const container = document.getElementById('historyTableContainer');
        container.innerHTML = '<div class="text-center text-muted py-4"><span class="spinner-border spinner-border-sm"></span> Загрузка...</div>';

        try {
            const response = await fetch(`/api/search-history?page=${page}`);
            const data = await response.json();

            if (response.ok && data.history) {
                currentHistoryData = data; // Сохраняем данные для быстрого доступа
                displaySearchHistory(data);
                // Если это первая загрузка, выбираем последний запрос
                if (page === 1 && data.history.length > 0) {
                    setTimeout(() => {
                        const firstRow = document.querySelector('.history-row[data-history-id]');
                        if (firstRow) {
                            const historyId = parseInt(firstRow.getAttribute('data-history-id'));
                            // Находим полные данные записи для отображения в форме
                            const selectedHistory = data.history.find(h => h.id === historyId);
                            if (selectedHistory) {
                                displayHistoryDetails(selectedHistory);
                            }
                            selectHistoryRecord(historyId, firstRow);
                        }
                    }, 100);
                } else {
                    // Скрываем форму, если нет записей на этой странице
                    if (data.history.length === 0) {
                        document.getElementById('historyDetailsRow').style.display = 'none';
                    }
                }
            } else {
                container.innerHTML = '<div class="text-center text-danger py-4">Ошибка при загрузке истории</div>';
                document.getElementById('historyDetailsRow').style.display = 'none';
            }
        } catch (error) {
            container.innerHTML = '<div class="text-center text-danger py-4">Ошибка: ' + error.message + '</div>';
            document.getElementById('historyDetailsRow').style.display = 'none';
        }
    }

    function displaySearchHistory(data) {
        const container = document.getElementById('historyTableContainer');

        if (data.history.length === 0) {
            container.innerHTML = '<div class="text-center text-muted py-4">История запросов пуста</div>';
            return;
        }

        let html = '<table class="table table-hover table-sm"><thead class="table-light"><tr>';
        html += '<th style="width: 8%;">ID</th>';
        html += '<th style="width: 15%;">Дата/Время</th>';
        html += '<th style="width: 28%;">RSS каналы</th>';
        html += '<th style="width: 25%;">Критерий отбора</th>';
        html += '<th style="width: 18%;">Статистика</th>';
        html += '<th style="width: 6%;">Действия</th>';
        html += '</tr></thead><tbody>';

        data.history.forEach(record => {
            const date = record.created_at ? new Date(record.created_at).toLocaleString('ru-RU') : 'Не указана';
            const rssFeeds = record.rss_feeds.split('\n').slice(0, 2).join(', ');
            const criteria = record.selection_criteria.length > 50 ? record.selection_criteria.substring(0, 50) + '...' : record.selection_criteria;
            const stats = record.results_data || {};
            const statsText = stats.total ? `${stats.total} статей, ${stats.relevant || 0} релевантных` : 'Нет данных';

            html += `<tr class="history-row" data-history-id="${record.id}">
                <td onclick="selectHistoryRecord(${record.id}, this.closest('tr'))" style="cursor: pointer;">${record.id}</td>
                <td onclick="selectHistoryRecord(${record.id}, this.closest('tr'))" style="cursor: pointer;"><small>${date}</small></td>
                <td onclick="selectHistoryRecord(${record.id}, this.closest('tr'))" style="cursor: pointer;"><small>${escapeHtml(rssFeeds)}</small></td>
                <td onclick="selectHistoryRecord(${record.id}, this.closest('tr'))" style="cursor: pointer;"><small>${escapeHtml(criteria)}</small></td>
                <td onclick="selectHistoryRecord(${record.id}, this.closest('tr'))" style="cursor: pointer;"><small>${statsText}</small></td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-danger" onclick="deleteHistoryRecord(${record.id}, event)" title="Удалить запрос и связанные статьи">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>`;
        });

        html += '</tbody></table>';

        // Пагинация
        if (data.total_pages > 1) {
            html += '<nav aria-label="Пагинация истории"><ul class="pagination justify-content-center mt-3">';

            // Предыдущая страница
            if (data.page > 1) {
                html += `<li class="page-item"><a class="page-link" href="#" onclick="loadSearchHistory(${data.page - 1}); return false;">Предыдущая</a></li>`;
            }

            // Номера страниц
            for (let i = 1; i <= data.total_pages; i++) {
                if (i === data.page) {
                    html += `<li class="page-item active"><span class="page-link">${i}</span></li>`;
                } else {
                    html += `<li class="page-item"><a class="page-link" href="#" onclick="loadSearchHistory(${i}); return false;">${i}</a></li>`;
                }
            }

            // Следующая страница
            if (data.page < data.total_pages) {
                html += `<li class="page-item"><a class="page-link" href="#" onclick="loadSearchHistory(${data.page + 1}); return false;">Следующая</a></li>`;
            }

            html += '</ul></nav>';
        }

        container.innerHTML = html;
    }

    // Выбор записи истории и загрузка статей
    async function selectHistoryRecord(historyId, eventElement = null) {
        // Выделение выбранной строки
        document.querySelectorAll('.history-row').forEach(row => {
            row.classList.remove('table-active');
        });
        if (eventElement) {
            eventElement.classList.add('table-active');
        } else {
            // Находим строку по data-history-id
            const row = document.querySelector(`.history-row[data-history-id="${historyId}"]`);
            if (row) {
                row.classList.add('table-active');
            }
        }

        // Загружаем детали истории из текущих данных или делаем запрос
        if (currentHistoryData && currentHistoryData.history) {
            const selectedHistory = currentHistoryData.history.find(h => h.id === historyId);
            if (selectedHistory) {
                displayHistoryDetails(selectedHistory);
            }
        } else {
            // Если данных нет, загружаем их
            try {
                const historyResponse = await fetch(`/api/search-history?page=${currentHistoryPage}`);
                const historyData = await historyResponse.json();

                if (historyResponse.ok && historyData.history) {
                    currentHistoryData = historyData;
                    const selectedHistory = historyData.history.find(h => h.id === historyId);
                    if (selectedHistory) {
                        displayHistoryDetails(selectedHistory);
                    }
                }
            } catch (error) {
                console.error('Ошибка при загрузке деталей истории:', error);
            }
        }

        const tbody = document.getElementById('historyArticlesTableBody');
        tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4"><span class="spinner-border spinner-border-sm"></span> Загрузка...</td></tr>';

        try {
            const response = await fetch(`/api/search-history/${historyId}/articles`);
            const data = await response.json();

            if (response.ok && data.articles) {
                displayHistoryArticles(data.articles);
            } else {
                tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger py-4">Ошибка при загрузке статей</td></tr>';
            }
        } catch (error) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-danger py-4">Ошибка: ' + error.message + '</td></tr>';
        }
    }

    // Отображение деталей истории в форме
    function displayHistoryDetails(history) {
        const detailsRow = document.getElementById('historyDetailsRow');
        detailsRow.style.display = 'block';

        // Заполняем поля формы
        document.getElementById('historyDetailId').value = history.id || '';

        if (history.created_at) {
            const date = new Date(history.created_at);
            document.getElementById('historyDetailDate').value = date.toLocaleString('ru-RU');
        } else {
            document.getElementById('historyDetailDate').value = 'Не указана';
        }

        document.getElementById('historyDetailLlmModel').value = history.llm_model || 'Не указано';
        document.getElementById('historyDetailTemperature').value = history.llm_temperature !== null && history.llm_temperature !== undefined ? history.llm_temperature : 'Не указано';
        document.getElementById('historyDetailThreshold').value = history.similarity_threshold !== null && history.similarity_threshold !== undefined ? history.similarity_threshold : 'Не указано';
        document.getElementById('historyDetailApiBase').value = history.openai_api_base || 'По умолчанию (OpenAI)';
        document.getElementById('historyDetailRssFeeds').value = history.rss_feeds || '';
        // Критерий отбора отображается в textarea, показываем полный текст
        document.getElementById('historyDetailCriteria').value = history.selection_criteria || '';

        // Статистика из results_data
        const stats = history.results_data || {};
        document.getElementById('historyDetailTotal').textContent = stats.total || 0;
        document.getElementById('historyDetailRelevant').textContent = stats.relevant || 0;
        document.getElementById('historyDetailDuplicates').textContent = stats.duplicates || 0;
        document.getElementById('historyDetailNonRelevant').textContent = stats.unique_non_relevant || 0;
    }

    function displayHistoryArticles(articles) {
        const tbody = document.getElementById('historyArticlesTableBody');

        if (articles.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">Статей не найдено</td></tr>';
            return;
        }

        tbody.innerHTML = '';

        articles.forEach(article => {
            // Основная строка
            const row = document.createElement('tr');
            row.className = 'news-article-group news-main-row';
            if (article.is_relevant) {
                row.classList.add('news-relevant', 'news-row-relevant');
            }

            // Форматирование даты
            let dateStr = 'Не указана';
            if (article.published_at) {
                const date = new Date(article.published_at);
                dateStr = date.toLocaleDateString('ru-RU', {
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit'
                });
            }

            // Форматирование релевантности
            const relevanceScore = article.relevance_score !== null ? (article.relevance_score * 100).toFixed(0) : '—';
            const relevanceBadgeClass = article.is_relevant ? 'bg-success' : 'bg-secondary';
            const relevanceText = article.is_relevant ? 'Релевантно' : 'Не релевантно';

            row.innerHTML = `
                <td class="align-middle">
                    <small class="text-muted">${article.id}</small>
                </td>
                <td class="align-middle">
                    <small class="news-meta">${escapeHtml(article.source)}</small>
                </td>
                <td class="align-middle">
                    <small class="news-meta">${dateStr}</small>
                </td>
                <td class="align-middle">
                    <div class="news-title">${escapeHtml(article.title)}</div>
                </td>
                <td class="align-middle">
                    <div>
                        <span class="badge ${relevanceBadgeClass} relevance-badge">${relevanceText}</span>
                        <small class="d-block text-muted mt-1">${relevanceScore}%</small>
                    </div>
                </td>
            `;
            tbody.appendChild(row);

            // Строка с содержанием (если есть)
            if (article.content && article.content.trim()) {
                const contentRow = document.createElement('tr');
                contentRow.className = 'news-article-group news-detail-row';
                contentRow.setAttribute('data-article-id', article.id);
                if (article.is_relevant) {
                    contentRow.classList.add('news-relevant', 'news-row-relevant');
                }
                const sanitizedContent = DOMPurify.sanitize(article.content, {
                    ALLOWED_TAGS: ['p', 'br', 'strong', 'em', 'u', 'a', 'ul', 'ol', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'blockquote', 'code', 'pre', 'div', 'span'],
                    ALLOWED_ATTR: ['href', 'target', 'rel', 'class']
                });
                contentRow.innerHTML = `
                    <td colspan="5" class="py-2 px-3">
                        <div class="news-content-full news-content-collapsed" id="history-content-${article.id}">${sanitizedContent}</div>
                        <div class="mt-2">
                            <span class="news-expand-btn text-primary" onclick="toggleArticleContent(${article.id}, this, 'history')">
                                <i class="bi bi-chevron-down" id="history-icon-${article.id}"></i> <span id="history-text-${article.id}">Развернуть</span>
                            </span>
                        </div>
                    </td>
                `;
                tbody.appendChild(contentRow);
            }

            // Строка с причиной классификации (если есть)
            if (article.classification_reason && article.classification_reason.trim()) {
                const reasonRow = document.createElement('tr');
                reasonRow.className = 'news-article-group news-detail-row';
                if (article.is_relevant) {
                    reasonRow.classList.add('news-relevant', 'news-row-relevant');
                }
                reasonRow.innerHTML = `
                    <td colspan="5" class="py-2 px-3">
                        <small class="text-muted">
                            <i class="bi bi-info-circle"></i> <strong>Причина:</strong> ${escapeHtml(article.classification_reason)}
                        </small>
                    </td>
                `;
                tbody.appendChild(reasonRow);
            }
        });
    }

    // Загрузка истории при переключении на вкладку
    const historyTab = document.getElementById('history-tab');
    if (historyTab) {
        historyTab.addEventListener('shown.bs.tab', function() {
            loadSearchHistory(currentHistoryPage);
        });
    }

    // Удаление записи из истории запросов
    async function deleteHistoryRecord(historyId, event) {
        // Останавливаем всплытие события, чтобы не срабатывал клик по строке
        if (event) {
            event.stopPropagation();
        }

        if (!confirm(`Вы уверены, что хотите удалить запрос #${historyId} и все связанные с ним статьи?\n\nЭто действие нельзя отменить!`)) {
            return;
        }

        try {
            const response = await fetch(`/api/search-history/${historyId}`, {
                method: 'DELETE'
            });

            const data = await response.json();

            if (response.ok && data.success) {
                // Если удаленная запись была выбрана, скрываем форму деталей
                const detailsRow = document.getElementById('historyDetailsRow');
                const selectedRow = document.querySelector('.history-row.table-active');
                if (selectedRow && selectedRow.getAttribute('data-history-id') == historyId) {
                    detailsRow.style.display = 'none';
                    // Очищаем таблицу статей
                    document.getElementById('historyArticlesTableBody').innerHTML = '<tr><td colspan="5" class="text-center text-muted py-4">Выберите запрос из истории</td></tr>';
                }

                // Перезагружаем историю
                loadSearchHistory(currentHistoryPage);

                // Обновляем общую статистику
                loadGeneralStatistics();

                // Показываем сообщение об успехе
                showSuccessMessage(`Запрос #${historyId} и связанные статьи успешно удалены`);
            } else {
                alert(data.error || 'Ошибка при удалении запроса');
            }
        } catch (error) {
            alert('Ошибка: ' + error.message);
        }
    }

    // Аккордеон для раскрытия/сворачивания контента статей
    function toggleArticleContent(articleId, buttonElement, prefix = '') {
        const contentId = prefix ? `history-content-${articleId}` : `content-${articleId}`;
        const iconId = prefix ? `history-icon-${articleId}` : `icon-${articleId}`;
        const textId = prefix ? `history-text-${articleId}` : `text-${articleId}`;
        const fullId = prefix ? `${prefix}-${articleId}` : articleId.toString();

        const contentDiv = document.getElementById(contentId);
        const icon = document.getElementById(iconId);
        const text = document.getElementById(textId);

        if (!contentDiv) return;

        // Если эта статья уже раскрыта, сворачиваем её
        if (expandedArticleId === fullId) {
            contentDiv.classList.remove('news-content-expanded');
            contentDiv.classList.add('news-content-collapsed');
            icon.className = 'bi bi-chevron-down';
            text.textContent = 'Развернуть';
            expandedArticleId = null;
            expandedArticlePrefix = null;
        } else {
            // Сворачиваем предыдущую раскрытую статью
            if (expandedArticleId !== null) {
                const prevContentId = expandedArticlePrefix ? `history-content-${expandedArticleId.split('-')[1]}` : `content-${expandedArticleId}`;
                const prevIconId = expandedArticlePrefix ? `history-icon-${expandedArticleId.split('-')[1]}` : `icon-${expandedArticleId}`;
                const prevTextId = expandedArticlePrefix ? `history-text-${expandedArticleId.split('-')[1]}` : `text-${expandedArticleId}`;

                const prevContent = document.getElementById(prevContentId);
                const prevIcon = document.getElementById(prevIconId);
                const prevText = document.getElementById(prevTextId);

                if (prevContent) {
                    prevContent.classList.remove('news-content-expanded');
                    prevContent.classList.add('news-content-collapsed');
                }
                if (prevIcon) {
                    prevIcon.className = 'bi bi-chevron-down';
                }
                if (prevText) {
                    prevText.textContent = 'Развернуть';
                }
            }

            // Раскрываем текущую статью
            contentDiv.classList.remove('news-content-collapsed');
            contentDiv.classList.add('news-content-expanded');
            icon.className = 'bi bi-chevron-up';
            text.textContent = 'Свернуть';
            expandedArticleId = fullId;
            expandedArticlePrefix = prefix;
        }
    }

    // Делаем функции доступными глобально
    window.deleteCurrentSearch = deleteCurrentSearch;
    window.loadSearchHistory = loadSearchHistory;
    window.selectHistoryRecord = selectHistoryRecord;
    window.deleteHistoryRecord = deleteHistoryRecord;
    window.toggleArticleContent = toggleArticleContent;
    window.loadNews = loadNews;
    window.loadGeneralStatistics = loadGeneralStatistics;
    window.loadStatisticsFromApi = loadStatisticsFromApi;
    window.escapeHtml = escapeHtml;

    // Загрузка новостей и статистики при загрузке страницы
    loadNews();
    loadGeneralStatistics();
});
