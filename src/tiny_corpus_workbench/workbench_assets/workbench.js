"use strict";

const status = document.getElementById("status");
fetch("/api/v0.5/workbench")
  .then((response) => response.json())
  .then((projection) => {
    status.textContent = `${projection.counts.record_count} record(s) ready.`;
  })
  .catch(() => {
    status.textContent = "The workbench projection is unavailable.";
  });
