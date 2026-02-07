import { ref } from "vue";

export interface ExportOptions {
  filename?: string;
  columns?: { key: string; label: string }[];
}

export function useExport() {
  const exporting = ref(false);

  /**
   * Convert data array to CSV string
   */
  const toCSV = (data: Record<string, any>[], columns?: { key: string; label: string }[]) => {
    if (!data.length) return "";

    // Determine columns
    const cols = columns || Object.keys(data[0]).map((key) => ({ key, label: key }));

    // Header row
    const header = cols.map((c) => `"${c.label.replace(/"/g, '""')}"`).join(",");

    // Data rows
    const rows = data.map((row) => {
      return cols
        .map((c) => {
          const value = row[c.key];
          if (value === null || value === undefined) return '""';
          if (typeof value === "object") return `"${JSON.stringify(value).replace(/"/g, '""')}"`;
          return `"${String(value).replace(/"/g, '""')}"`;
        })
        .join(",");
    });

    return [header, ...rows].join("\n");
  };

  /**
   * Convert data to JSON string
   */
  const toJSON = (data: Record<string, any>[]) => {
    return JSON.stringify(data, null, 2);
  };

  /**
   * Download data as file
   */
  const download = (content: string, filename: string, mimeType: string) => {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  };

  /**
   * Export data as CSV
   */
  const exportCSV = async (data: Record<string, any>[], options: ExportOptions = {}) => {
    exporting.value = true;
    try {
      const csv = toCSV(data, options.columns);
      const filename = options.filename || `export_${Date.now()}.csv`;
      download(csv, filename, "text/csv;charset=utf-8;");
      return true;
    } finally {
      exporting.value = false;
    }
  };

  /**
   * Export data as JSON
   */
  const exportJSON = async (data: Record<string, any>[], options: ExportOptions = {}) => {
    exporting.value = true;
    try {
      const json = toJSON(data);
      const filename = options.filename || `export_${Date.now()}.json`;
      download(json, filename, "application/json");
      return true;
    } finally {
      exporting.value = false;
    }
  };

  /**
   * Export single item as JSON config
   */
  const exportConfig = async (data: Record<string, any>, options: ExportOptions = {}) => {
    exporting.value = true;
    try {
      const json = JSON.stringify(data, null, 2);
      const filename = options.filename || `config_${Date.now()}.json`;
      download(json, filename, "application/json");
      return true;
    } finally {
      exporting.value = false;
    }
  };

  return {
    exporting,
    exportCSV,
    exportJSON,
    exportConfig,
    toCSV,
    toJSON,
  };
}
