(() => {
    "use strict";

    function readCookie(name) {
        const cookieString = `; ${document.cookie}`;
        const parts = cookieString.split(`; ${name}=`);
        if (parts.length !== 2) {
            return "";
        }
        return decodeURIComponent(parts.pop().split(";").shift());
    }

    async function saveOrder(url, payload) {
        const response = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": readCookie("csrftoken"),
                "X-Requested-With": "XMLHttpRequest",
            },
            body: JSON.stringify(payload),
        });
        const result = await response.json().catch(() => ({}));
        if (!response.ok || !result.ok) {
            throw new Error(result.message || "정렬 순서를 저장하지 못했습니다.");
        }
    }

    function getElementTarget(event, selector) {
        if (!(event.target instanceof Element)) {
            return null;
        }
        return event.target.closest(selector);
    }

    function clearDragMarkers(elements) {
        elements.forEach((element) => {
            element.classList.remove("is-drag-over", "is-dragging");
        });
    }

    function initFolderDragAndDrop() {
        const folderList = document.querySelector("[data-folder-reorder-url]");
        if (!folderList) {
            return;
        }

        const folderCards = () => Array.from(folderList.children)
            .filter((child) => child.classList.contains("owned-folder-group"));
        let draggedFolder = null;

        folderList.querySelectorAll(".folder-drag-handle[draggable='true']")
            .forEach((handle) => {
                handle.addEventListener("dragstart", (event) => {
                    draggedFolder = handle.closest(".owned-folder-group");
                    if (!draggedFolder) {
                        return;
                    }
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData(
                        "text/plain",
                        draggedFolder.dataset.folderId || "",
                    );
                    requestAnimationFrame(() => {
                        draggedFolder.classList.add("is-dragging");
                    });
                });

                handle.addEventListener("dragend", () => {
                    clearDragMarkers([folderList, ...folderCards()]);
                    draggedFolder = null;
                });
            });

        folderList.addEventListener("dragover", (event) => {
            if (!draggedFolder) {
                return;
            }
            event.preventDefault();
            const target = getElementTarget(event, ".owned-folder-group");
            if (target && target !== draggedFolder && target.parentElement === folderList) {
                const midpoint = target.getBoundingClientRect().top
                    + target.getBoundingClientRect().height / 2;
                const reference = event.clientY < midpoint
                    ? target
                    : target.nextElementSibling;
                if (reference !== draggedFolder) {
                    if (reference) {
                        folderList.insertBefore(draggedFolder, reference);
                    } else {
                        folderList.appendChild(draggedFolder);
                    }
                }
            }
            folderList.classList.add("is-drag-over");
        });

        folderList.addEventListener("dragleave", (event) => {
            if (!folderList.contains(event.relatedTarget)) {
                folderList.classList.remove("is-drag-over");
            }
        });

        folderList.addEventListener("drop", async (event) => {
            if (!draggedFolder) {
                return;
            }
            event.preventDefault();
            const orderedFolderIds = folderCards()
                .map((card) => card.dataset.folderId)
                .filter(Boolean);
            clearDragMarkers([folderList, ...folderCards()]);
            draggedFolder = null;
            if (!orderedFolderIds.length) {
                return;
            }

            try {
                await saveOrder(folderList.dataset.folderReorderUrl, {
                    folder_ids: orderedFolderIds,
                });
                window.location.reload();
            } catch (error) {
                window.alert(error.message);
                window.location.reload();
            }
        });
    }

    function initSeriesDragAndDrop() {
        const seriesLists = Array.from(
            document.querySelectorAll("[data-series-reorder-url]"),
        );
        if (!seriesLists.length) {
            return;
        }

        let draggedRow = null;
        let sourceList = null;

        const rowsIn = (list) => Array.from(list.children)
            .filter((child) => child.classList.contains("owned-volume-row"));
        const allRows = () => seriesLists.flatMap((list) => rowsIn(list));
        const clearSeriesState = () => {
            clearDragMarkers([...seriesLists, ...allRows()]);
            draggedRow = null;
            sourceList = null;
        };

        document.querySelectorAll(
            ".series-drag-area[draggable='true'], .series-drag-handle[draggable='true']",
        )
            .forEach((handle) => {
                handle.addEventListener("dragstart", (event) => {
                    draggedRow = handle.closest(".owned-volume-row");
                    sourceList = draggedRow?.closest(".owned-volume-list");
                    if (!draggedRow || !sourceList) {
                        return;
                    }
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData(
                        "text/plain",
                        draggedRow.dataset.ownedSeriesId || "",
                    );
                    requestAnimationFrame(() => {
                        draggedRow.classList.add("is-dragging");
                    });
                });

                handle.addEventListener("dragend", clearSeriesState);
            });

        seriesLists.forEach((list) => {
            list.addEventListener("dragover", (event) => {
                if (!draggedRow) {
                    return;
                }
                event.preventDefault();
                const target = getElementTarget(event, ".owned-volume-row");
                if (target && target !== draggedRow && target.parentElement === list) {
                    const rect = target.getBoundingClientRect();
                    const reference = event.clientY < rect.top + rect.height / 2
                        ? target
                        : target.nextElementSibling;
                    if (reference !== draggedRow) {
                        if (reference) {
                            list.insertBefore(draggedRow, reference);
                        } else {
                            list.appendChild(draggedRow);
                        }
                    }
                } else if (!target && draggedRow.parentElement !== list) {
                    list.appendChild(draggedRow);
                }
                seriesLists.forEach((seriesList) => {
                    seriesList.classList.toggle("is-drag-over", seriesList === list);
                });
            });

            list.addEventListener("dragleave", (event) => {
                if (!list.contains(event.relatedTarget)) {
                    list.classList.remove("is-drag-over");
                }
            });

            list.addEventListener("drop", async (event) => {
                if (!draggedRow) {
                    return;
                }
                event.preventDefault();
                const movedId = draggedRow.dataset.ownedSeriesId;
                const orderedSeriesIds = rowsIn(list)
                    .map((row) => row.dataset.ownedSeriesId)
                    .filter(Boolean);
                const targetFolderId = list.dataset.folderId || null;
                clearSeriesState();
                if (!orderedSeriesIds.length) {
                    return;
                }

                try {
                    await saveOrder(list.dataset.seriesReorderUrl, {
                        folder_id: targetFolderId,
                        owned_series_ids: orderedSeriesIds,
                        moved_owned_series_id: movedId,
                    });
                    window.location.reload();
                } catch (error) {
                    window.alert(error.message);
                    window.location.reload();
                }
            });
        });
    }

    initFolderDragAndDrop();
    initSeriesDragAndDrop();
})();
