import { useEffect, useMemo, useState } from "react";

import {
  ArrowRight,
  Check,
  File,
  FileArchive,
  FileAudio,
  FileCode,
  FileImage,
  FileText,
  FileVideo,
  Folder,
  FolderOpen,
  LoaderCircle,
  RefreshCw,
  ShieldCheck,
  LockKeyhole,
  Search,
  Eye,
  X,
  ChevronLeft,
  ChevronRight,
  Download,
  Sun,
  Moon,
  Sparkles,
  Monitor,
  HardDrive,
  ShieldCheck as Shield,
} from "lucide-react";

const GROUPS = [
  {
    id: "Documents",
    icon: FileText,
    subs: {
      PDFs: ["pdf"],
      Word: ["doc", "docx", "odt", "rtf"],
      Excel: ["xls", "xlsx", "ods"],
      PowerPoint: ["ppt", "pptx", "odp"],
      Text: ["txt", "md"],
      Data: ["csv", "json", "xml"],
    },
  },
  {
    id: "Images",
    icon: FileImage,
    subs: {
      Photos: ["jpg", "jpeg", "png", "gif", "webp", "heic", "bmp"],
      Vector: ["svg", "ai", "eps"],
      Design: ["psd", "sketch", "fig"],
    },
  },
  {
    id: "Videos",
    icon: FileVideo,
    subs: {
      Videos: ["mp4", "mkv", "mov", "avi", "webm", "m4v"],
    },
  },
  {
    id: "Audio",
    icon: FileAudio,
    subs: {
      Music: ["mp3", "aac", "m4a", "flac", "ogg", "wma"],
      Recordings: ["wav", "aiff"],
    },
  },
  {
    id: "Archives",
    icon: FileArchive,
    subs: {
      Compressed: ["zip", "rar", "7z", "tar", "gz", "bz2"],
    },
  },
  {
    id: "Code",
    icon: FileCode,
    subs: {
      Web: ["html", "css", "js", "jsx", "ts", "tsx"],
      Programming: ["py", "java", "cpp", "c", "cs", "go", "rs", "php"],
    },
  },
  {
    id: "Others",
    icon: File,
    subs: {
      Unsorted: [],
    },
  },
];

const PAGE_SIZE = 25;

const extOf = (name) =>
  name.includes(".") ? name.split(".").pop().toLowerCase() : "";

const classify = (name) => {
  const ext = extOf(name);

  for (const group of GROUPS) {
    for (const [subcategory, extensions] of Object.entries(group.subs)) {
      if (extensions.includes(ext)) {
        return {
          category: group.id,
          subcategory,
        };
      }
    }
  }

  return {
    category: "Others",
    subcategory: "Unsorted",
  };
};

const formatBytes = (bytes) => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 ** 2) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(2)} GB`;
};

function getClientId() {
  let id = localStorage.getItem("desksweep_client_id");

  if (!id) {
    id = crypto.randomUUID();
    localStorage.setItem("desksweep_client_id", id);
  }

  return id;
}

function getFileIcon(category) {
  return GROUPS.find((group) => group.id === category)?.icon || File;
}

export default function App() {
  const [directory, setDirectory] = useState(null);
  const [files, setFiles] = useState([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  const [activeCategory, setActiveCategory] = useState("All");
  const [activeSub, setActiveSub] = useState("All");

  const [access, setAccess] = useState(null);
  const [paying, setPaying] = useState(false);

  const [searchQuery, setSearchQuery] = useState("");
  const [currentPage, setCurrentPage] = useState(1);

  const [previewFile, setPreviewFile] = useState(null);
  const [previewUrl, setPreviewUrl] = useState("");

  const [privacyOpen, setPrivacyOpen] = useState(false);

  const [theme, setTheme] = useState(
    () => localStorage.getItem("desksweep_theme") || "light",
  );

  const clientId = useMemo(() => getClientId(), []);

  const supported =
    typeof window !== "undefined" && "showDirectoryPicker" in window;

  const totalSize = files.reduce((sum, file) => sum + file.size, 0);

  const counts = Object.fromEntries(
    GROUPS.map((group) => [
      group.id,
      files.filter((file) => file.category === group.id).length,
    ]),
  );

  const visibleFiles = files.filter(
    (file) =>
      (activeCategory === "All" || file.category === activeCategory) &&
      (activeSub === "All" || file.subcategory === activeSub),
  );

  const searchedFiles = visibleFiles.filter((file) =>
    file.name.toLowerCase().includes(searchQuery.trim().toLowerCase()),
  );

  const totalPages = Math.max(1, Math.ceil(searchedFiles.length / PAGE_SIZE));

  const pageFiles = searchedFiles.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE,
  );

  const selectedGroup = GROUPS.find((group) => group.id === activeCategory);

  const subcategories = selectedGroup ? Object.keys(selectedGroup.subs) : [];

  const locked =
    access?.payment_required ||
    (!access?.is_pro && access?.attempts_remaining === 0);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem("desksweep_theme", theme);
  }, [theme]);

  useEffect(() => {
    refreshAccess();
  }, []);

  useEffect(() => {
    setCurrentPage(1);
  }, [activeCategory, activeSub, searchQuery]);

  useEffect(() => {
    return () => {
      if (previewUrl) URL.revokeObjectURL(previewUrl);
    };
  }, [previewUrl]);

  async function refreshAccess() {
    try {
      const response = await fetch(`/api/access/${clientId}`);

      if (!response.ok) {
        throw new Error("Could not check your plan.");
      }

      const data = await response.json();
      setAccess(data);
      return data;
    } catch {
      setMessage(
        "Cannot reach the DeskSweep server. Please check that the backend is running.",
      );
      return null;
    }
  }

  async function requestWrite(handle) {
    let permission = await handle.queryPermission({
      mode: "readwrite",
    });

    if (permission !== "granted") {
      permission = await handle.requestPermission({
        mode: "readwrite",
      });
    }

    if (permission !== "granted") {
      throw new Error("Folder permission was not granted.");
    }
  }

  async function selectFolder() {
    setMessage("");

    if (!supported) {
      setMessage(
        "Folder access requires the latest Chrome or Edge on desktop.",
      );
      return;
    }

    try {
      const handle = await window.showDirectoryPicker({
        mode: "readwrite",
      });

      await requestWrite(handle);

      closePreview();

      setDirectory(handle);
      setFiles([]);
      setSearchQuery("");
      setCurrentPage(1);
      setActiveCategory("All");
      setActiveSub("All");
    } catch (error) {
      if (error.name !== "AbortError") {
        setMessage(error.message || "Could not select folder.");
      }
    }
  }

  async function scanFolder() {
    if (!directory || busy) return;

    setBusy(true);
    setMessage("");

    try {
      await requestWrite(directory);

      const found = [];

      for await (const [name, handle] of directory.entries()) {
        if (handle.kind !== "file") continue;

        const file = await handle.getFile();

        found.push({
          id: `${name}-${file.lastModified}`,
          name,
          size: file.size,
          handle,
          ...classify(name),
        });
      }

      found.sort((a, b) => a.name.localeCompare(b.name));

      setFiles(found);
      setActiveCategory("All");
      setActiveSub("All");
      setSearchQuery("");
      setCurrentPage(1);

      if (!found.length) {
        setMessage("No files found directly inside this folder.");
      } else {
        setMessage(`Successfully scanned ${found.length} files.`);
      }

      await refreshAccess();
    } catch (error) {
      setMessage(error.message || "Folder scan failed.");
    } finally {
      setBusy(false);
    }
  }

  async function openPreview(item) {
    try {
      closePreview();

      const file = await item.handle.getFile();
      const url = URL.createObjectURL(file);

      setPreviewFile({
        ...item,
        file,
      });

      setPreviewUrl(url);
    } catch (error) {
      setMessage(error.message || "Could not preview this file.");
    }
  }

  function closePreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    setPreviewUrl("");
    setPreviewFile(null);
  }

  async function uniqueName(folderHandle, originalName) {
    const dot = originalName.lastIndexOf(".");
    const base = dot > 0 ? originalName.slice(0, dot) : originalName;
    const ext = dot > 0 ? originalName.slice(dot) : "";

    let candidate = originalName;
    let i = 1;

    while (true) {
      try {
        await folderHandle.getFileHandle(candidate);
        candidate = `${base} (${i++})${ext}`;
      } catch {
        return candidate;
      }
    }
  }

  async function organizeFiles() {
    if (!directory || !files.length || busy) return;

    let currentAccess = access;

    if (!currentAccess) {
      currentAccess = await refreshAccess();
    }

    if (!currentAccess) {
      setMessage("Could not verify your plan. Please try again.");
      return;
    }

    if (
      currentAccess.payment_required ||
      (!currentAccess.is_pro && currentAccess.attempts_remaining === 0)
    ) {
      setMessage(
        "Your 2 free organization attempts are used. Unlock Pro for ₹99.",
      );
      return;
    }

    const confirmed = window.confirm(
      `Organize ${files.length} files into category and subcategory folders? Existing files will not be overwritten.`,
    );

    if (!confirmed) return;

    setBusy(true);
    setMessage("");

    let moved = 0;
    let failed = 0;

    try {
      await requestWrite(directory);

      for (const item of files) {
        try {
          const categoryHandle = await directory.getDirectoryHandle(
            item.category,
            { create: true },
          );

          const subHandle = await categoryHandle.getDirectoryHandle(
            item.subcategory,
            { create: true },
          );

          const targetName = await uniqueName(subHandle, item.name);
          const sourceBlob = await item.handle.getFile();

          const target = await subHandle.getFileHandle(targetName, {
            create: true,
          });

          const writable = await target.createWritable();

          await writable.write(sourceBlob);
          await writable.close();

          // Delete source only after destination write succeeds.
          await directory.removeEntry(item.name);

          moved++;
        } catch (error) {
          console.error("Could not organize file:", item.name, error);
          failed++;
        }
      }

      if (moved > 0 && !currentAccess.is_pro) {
        const usage = await fetch("/api/usage/complete", {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            client_id: clientId,
          }),
        });

        if (!usage.ok) {
          throw new Error("Files were moved, but usage could not be recorded.");
        }

        setAccess(await usage.json());
      } else {
        await refreshAccess();
      }

      await scanFolderAfterOrganization();

      setMessage(
        `${moved} files organized successfully · ${failed} could not be moved.`,
      );
    } catch (error) {
      setMessage(error.message || "Organization failed.");
    } finally {
      setBusy(false);
    }
  }

  async function scanFolderAfterOrganization() {
    const remaining = [];

    for await (const [name, handle] of directory.entries()) {
      if (handle.kind !== "file") continue;

      const file = await handle.getFile();

      remaining.push({
        id: `${name}-${file.lastModified}`,
        name,
        size: file.size,
        handle,
        ...classify(name),
      });
    }

    remaining.sort((a, b) => a.name.localeCompare(b.name));
    setFiles(remaining);
  }

  async function startPayment() {
    setPaying(true);
    setMessage("");

    try {
      const orderResponse = await fetch("/api/payments/create-order", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_id: clientId,
        }),
      });

      const order = await orderResponse.json();

      if (!orderResponse.ok) {
        throw new Error(order.detail || "Could not create payment order.");
      }

      if (order.already_pro) {
        await refreshAccess();
        setMessage("DeskSweep Pro is already unlocked.");
        return;
      }

      if (!window.Razorpay) {
        throw new Error(
          "Razorpay Checkout did not load. Check your internet connection.",
        );
      }

      const checkout = new window.Razorpay({
        key: order.key_id,
        amount: order.amount,
        currency: order.currency,
        name: order.name,
        description: order.description,
        order_id: order.order_id,

        theme: {
          color: "#286b43",
        },

        handler: async (response) => {
          try {
            const verify = await fetch("/api/payments/verify", {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                client_id: clientId,
                razorpay_order_id: response.razorpay_order_id,
                razorpay_payment_id: response.razorpay_payment_id,
                razorpay_signature: response.razorpay_signature,
              }),
            });

            const result = await verify.json();

            if (!verify.ok) {
              throw new Error(result.detail || "Payment verification failed.");
            }

            setAccess(result);
            setMessage("Payment verified. DeskSweep Pro unlocked!");
          } catch (error) {
            setMessage(error.message);
          }
        },

        modal: {
          ondismiss: () => {
            setMessage("Payment window closed. No access was unlocked.");
          },
        },
      });

      checkout.open();
    } catch (error) {
      setMessage(error.message);
    } finally {
      setPaying(false);
    }
  }

  function renderPreview() {
    if (!previewFile || !previewUrl) return null;

    const file = previewFile.file;
    const name = previewFile.name.toLowerCase();

    const isText =
      /\.(txt|md|json|xml|csv|js|jsx|ts|tsx|css|html|py|java|c|cpp|log)$/i.test(
        name,
      );

    return (
      <div className="preview-backdrop" onClick={closePreview}>
        <aside
          className="preview-drawer"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="preview-header">
            <div>
              <div className="label">FILE PREVIEW</div>
              <strong title={previewFile.name}>{previewFile.name}</strong>
            </div>

            <button
              className="preview-close"
              onClick={closePreview}
              aria-label="Close preview"
            >
              <X size={18} />
            </button>
          </div>

          <div className="preview-meta">
            {previewFile.category} · {formatBytes(previewFile.size)}
          </div>

          <div className="preview-content">
            {file.type.startsWith("image/") ? (
              <img src={previewUrl} alt={previewFile.name} />
            ) : file.type === "application/pdf" || name.endsWith(".pdf") ? (
              <iframe src={previewUrl} title={previewFile.name} />
            ) : file.type.startsWith("video/") ? (
              <video src={previewUrl} controls />
            ) : file.type.startsWith("audio/") ? (
              <audio src={previewUrl} controls />
            ) : isText ? (
              <iframe src={previewUrl} title={previewFile.name} />
            ) : (
              <div className="preview-unsupported">
                <File size={32} />
                <strong>Preview not available</strong>
                <span>
                  This file format cannot be previewed in your browser.
                </span>
              </div>
            )}
          </div>

          <a
            className="preview-download"
            href={previewUrl}
            download={previewFile.name}
          >
            <Download size={15} />
            Download file
          </a>
        </aside>
      </div>
    );
  }

  function renderPrivacyPolicy() {
    if (!privacyOpen) return null;

    return (
      <div className="privacy-backdrop" onClick={() => setPrivacyOpen(false)}>
        <section
          className="privacy-modal"
          onClick={(event) => event.stopPropagation()}
        >
          <div className="privacy-heading">
            <div>
              <span className="label">YOUR PRIVACY MATTERS</span>
              <h2>Privacy Policy</h2>
              <p>Last updated: November 15, 2026</p>
            </div>

            <button
              className="preview-close"
              onClick={() => setPrivacyOpen(false)}
              aria-label="Close privacy policy"
            >
              <X size={18} />
            </button>
          </div>

          <div className="privacy-body">
            <h3>1. Overview</h3>
            <p>
              DeskSweep is a browser-based file organization tool. We aim to
              keep your files on your device and collect only the limited
              information needed to operate the service.
            </p>

            <h3>2. Your Files</h3>
            <p>
              Files in the folder you select are accessed by your browser after
              you grant permission. Scanning, previewing and organizing happen
              locally in your browser. DeskSweep does not intentionally upload
              your selected file contents to its backend or store those contents
              in its database.
            </p>

            <h3>3. Information We Store</h3>
            <p>
              DeskSweep stores an anonymous browser client identifier, usage
              attempts, Pro access status and payment-related order and
              transaction identifiers needed to manage purchases.
            </p>

            <h3>4. Payments</h3>
            <p>
              Payments are processed by Razorpay. Payment details are handled
              according to Razorpay's own terms and privacy policy. DeskSweep
              does not ask for or store your UPI PIN.
            </p>

            <h3>5. Browser Storage</h3>
            <p>
              Local storage is used to remember your anonymous client identifier
              and your light or dark theme preference. Clearing browser storage
              may reset your local identifier.
            </p>

            <h3>6. Permissions</h3>
            <p>
              You choose which folder to share with the browser. DeskSweep can
              access that selected folder only within the permissions granted by
              your browser.
            </p>

            <h3>7. Third-Party Services</h3>
            <p>
              DeskSweep uses Razorpay for payments and may use hosting, font or
              other infrastructure providers. Those providers may process
              technical information under their own policies.
            </p>

            <h3>8. Data Retention</h3>
            <p>
              Anonymous usage and payment records may be retained as needed to
              provide the service, manage purchases and maintain appropriate
              business records.
            </p>

            <h3>9. Contact</h3>
            <p>
              For privacy questions, contact the DeskSweep support team using
              the official support email published on the DeskSweep website.
            </p>
          </div>

          <button
            className="privacy-done"
            onClick={() => setPrivacyOpen(false)}
          >
            Got it
          </button>
        </section>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <header className="topbar">
        <a className="brand" href="#">
          <span className="brand-icon">
            <FolderOpen size={19} />
          </span>
          <span>DeskSweep</span>
          <span className="brand-beta">BETA</span>
        </a>

        <div className="topbar-right">
          <div className="topbar-note">
            <ShieldCheck size={15} />
            Your files stay on your device
          </div>

          <button
            className="theme-toggle"
            onClick={() =>
              setTheme((current) => (current === "light" ? "dark" : "light"))
            }
            aria-label="Toggle theme"
            title={theme === "light" ? "Dark mode" : "Light mode"}
          >
            {theme === "light" ? <Moon size={17} /> : <Sun size={17} />}
          </button>
        </div>
      </header>

      <main className="main">
        <section className="intro">
          <div className="overline">
            <Sparkles size={13} />A CLEARER DIGITAL WORKSPACE
          </div>

          <h1>
            Less clutter.
            <br />
            <span>More clarity.</span>
          </h1>

          <p>
            Your files deserve a little organization. DeskSweep scans your
            selected folder, sorts files into meaningful categories and helps
            you bring order to your digital workspace — without uploading your
            documents.
          </p>

          <div className="trust-points">
            <span>
              <ShieldCheck size={15} />
              Local file processing
            </span>
            <span>
              <Check size={15} />
              No file-content uploads
            </span>
            <span>
              <Folder size={15} />
              Your folders, your control
            </span>
          </div>
        </section>

        <section className="organizer-card">
          <div className="card-topline">
            <div>
              <div className="label">GET STARTED</div>
              <h2>
                {directory ? directory.name : "Choose a folder to organize"}
              </h2>
              <p className="card-description">
                Select a folder and let DeskSweep do the sorting.
              </p>
            </div>

            <button
              className="select-button"
              onClick={selectFolder}
              disabled={busy}
            >
              <Folder size={16} />
              {directory ? "Change folder" : "Select folder"}
            </button>
          </div>

          <div className={`folder-status ${directory ? "is-ready" : ""}`}>
            <span className="status-icon">
              <FolderOpen size={20} />
            </span>

            <div className="status-copy">
              <strong>
                {directory ? "Folder connected" : "You stay in control"}
              </strong>

              <span>
                {directory
                  ? "Ready to scan files in this folder"
                  : "Choose Desktop, Downloads or any folder you want"}
              </span>
            </div>

            {directory && (
              <span className="ready-check">
                <Check size={15} />
              </span>
            )}
          </div>

          {!supported && (
            <div className="browser-warning">
              <Shield size={15} />
              Use the latest Google Chrome or Microsoft Edge on desktop for
              folder access.
            </div>
          )}

          <button
            className="scan-button"
            onClick={scanFolder}
            disabled={!directory || busy}
          >
            {busy ? (
              <LoaderCircle className="spin" size={17} />
            ) : (
              <RefreshCw size={16} />
            )}

            {busy ? "Working..." : "Scan selected folder"}

            {!busy && <ArrowRight size={17} />}
          </button>

          {message && <div className="message">{message}</div>}
        </section>

        {files.length > 0 && (
          <section className="results">
            <div className="results-top">
              <div>
                <div className="label">YOUR FILE OVERVIEW</div>
                <h2>Everything in its place.</h2>
                <p className="section-description">
                  Review your files before organizing them.
                </p>
              </div>

              <div className="totals">
                <strong>{files.length}</strong> files
                <span>·</span> {formatBytes(totalSize)}
              </div>
            </div>

            <div className="category-list">
              <button
                className={`category-chip ${
                  activeCategory === "All" ? "selected" : ""
                }`}
                onClick={() => {
                  setActiveCategory("All");
                  setActiveSub("All");
                }}
              >
                All <strong>{files.length}</strong>
              </button>

              {GROUPS.map(({ id, icon: Icon }) => (
                <button
                  key={id}
                  className={`category-chip ${
                    activeCategory === id ? "selected" : ""
                  }`}
                  onClick={() => {
                    setActiveCategory(id);
                    setActiveSub("All");
                  }}
                >
                  <Icon size={15} />
                  {id}
                  <strong>{counts[id]}</strong>
                </button>
              ))}
            </div>

            {selectedGroup && (
              <div className="subcategory-list">
                {subcategories.map((sub) => (
                  <button
                    key={sub}
                    className={`subcategory-chip ${
                      activeSub === sub ? "selected" : ""
                    }`}
                    onClick={() =>
                      setActiveSub(activeSub === sub ? "All" : sub)
                    }
                  >
                    {sub}
                  </button>
                ))}
              </div>
            )}

            <div className="file-panel">
              <div className="file-panel-head">
                <strong>
                  {activeCategory === "All"
                    ? "Files ready to organize"
                    : `${activeCategory}${
                        activeSub !== "All" ? " / " + activeSub : ""
                      }`}
                </strong>

                <span>{searchedFiles.length} items</span>
              </div>

              <div className="file-toolbar">
                <div className="file-search">
                  <Search size={15} />

                  <input
                    value={searchQuery}
                    onChange={(event) => setSearchQuery(event.target.value)}
                    placeholder="Search your files..."
                    aria-label="Search files"
                  />

                  {searchQuery && (
                    <button
                      className="clear-search"
                      onClick={() => setSearchQuery("")}
                      aria-label="Clear search"
                    >
                      <X size={14} />
                    </button>
                  )}
                </div>

                <span className="page-size-note">
                  Showing up to 25 files per page
                </span>
              </div>

              <div className="file-list">
                {pageFiles.map((item) => {
                  const Icon = getFileIcon(item.category);

                  return (
                    <div className="file-row" key={item.id}>
                      <span
                        className={`file-type-icon type-${item.category.toLowerCase()}`}
                      >
                        <Icon size={16} />
                      </span>

                      <span className="file-name" title={item.name}>
                        {item.name}
                      </span>

                      <span className="file-category-label">
                        {item.category} / {item.subcategory}
                      </span>

                      <span className="file-size">
                        {formatBytes(item.size)}
                      </span>

                      <button
                        className="preview-button"
                        onClick={() => openPreview(item)}
                        title={`Preview ${item.name}`}
                        aria-label={`Preview ${item.name}`}
                      >
                        <Eye size={16} />
                      </button>
                    </div>
                  );
                })}

                {!searchedFiles.length && (
                  <div className="empty-list">No matching files found.</div>
                )}
              </div>

              {searchedFiles.length > 0 && (
                <div className="pagination">
                  <span>
                    Showing {(currentPage - 1) * PAGE_SIZE + 1}–
                    {Math.min(currentPage * PAGE_SIZE, searchedFiles.length)} of{" "}
                    {searchedFiles.length}
                  </span>

                  <div className="pagination-controls">
                    <button
                      onClick={() =>
                        setCurrentPage((page) => Math.max(1, page - 1))
                      }
                      disabled={currentPage === 1}
                      aria-label="Previous page"
                    >
                      <ChevronLeft size={16} />
                    </button>

                    <strong>
                      {currentPage} / {totalPages}
                    </strong>

                    <button
                      onClick={() =>
                        setCurrentPage((page) => Math.min(totalPages, page + 1))
                      }
                      disabled={currentPage === totalPages}
                      aria-label="Next page"
                    >
                      <ChevronRight size={16} />
                    </button>
                  </div>
                </div>
              )}

              <div className="organize-footer">
                <div className="organize-copy">
                  <strong>Ready for a cleaner workspace?</strong>
                  <span>
                    Files are sorted into category folders. Existing files are
                    not intentionally overwritten.
                  </span>
                </div>

                <button
                  className="organize-button"
                  onClick={organizeFiles}
                  disabled={busy || !files.length || locked}
                >
                  {busy ? (
                    <LoaderCircle className="spin" size={16} />
                  ) : (
                    <Check size={16} />
                  )}
                  Organize files
                </button>
              </div>
            </div>
          </section>
        )}

        <section className="bottom-row">
          <div className="usage-card">
            <div className="plan-icon">
              <Sparkles size={17} />
            </div>

            <div className="label">YOUR PLAN</div>

            <strong>{access?.is_pro ? "DeskSweep Pro" : "Free plan"}</strong>

            <span>
              {access?.is_pro
                ? "Unlimited file organization"
                : access
                  ? `${access.attempts_remaining} of 2 free attempts remaining`
                  : "Loading your plan..."}
            </span>
          </div>

          {locked && (
            <div className="pay-card">
              <div>
                <div className="label">ONE-TIME PURCHASE</div>
                <strong>Make organization unlimited.</strong>
                <span>Unlock DeskSweep Pro. No recurring subscription.</span>
              </div>

              <button
                className="pay-button"
                onClick={startPayment}
                disabled={paying}
              >
                {paying ? (
                  <LoaderCircle className="spin" size={16} />
                ) : (
                  <LockKeyhole size={16} />
                )}
                Unlock for ₹99
              </button>
            </div>
          )}
        </section>

        <section className="privacy-promise">
          <div className="privacy-promise-icon">
            <ShieldCheck size={19} />
          </div>

          <div>
            <strong>Your files are yours. Always.</strong>
            <p>
              File scanning, previewing and organization happen in your browser.
              DeskSweep stores limited anonymous usage and payment records, not
              your file contents.
            </p>
          </div>

          <button onClick={() => setPrivacyOpen(true)}>
            Learn more
            <ArrowRight size={14} />
          </button>
        </section>

        <section className="how-it-works">
          <div className="label">SIMPLE BY DESIGN</div>
          <h2>A little order goes a long way.</h2>

          <div className="steps-grid">
            <div className="step-card">
              <span className="step-number">01</span>
              <div className="step-icon">
                <FolderOpen size={21} />
              </div>
              <h3>Choose a folder</h3>
              <p>
                Select the folder you want DeskSweep to organize. You decide
                what it can access.
              </p>
            </div>

            <div className="step-card">
              <span className="step-number">02</span>
              <div className="step-icon">
                <Search size={21} />
              </div>
              <h3>Scan and review</h3>
              <p>
                Files are identified by type. Review the results before making
                any changes.
              </p>
            </div>

            <div className="step-card">
              <span className="step-number">03</span>
              <div className="step-icon">
                <Check size={21} />
              </div>
              <h3>Organize</h3>
              <p>
                Confirm the action and let DeskSweep arrange files into clear
                category folders.
              </p>
            </div>
          </div>
        </section>

        <div className="footnote">
          <ShieldCheck size={14} />
          Your selected files are processed locally in your browser. Only
          anonymous usage and payment status are sent to DeskSweep.
        </div>
      </main>

      {renderPreview()}
      {renderPrivacyPolicy()}

      <footer className="site-footer">
        <div className="footer-brand">
          <a className="footer-logo" href="#">
            <span className="brand-icon">
              <FolderOpen size={17} />
            </span>
            DeskSweep
          </a>
          <span>Less clutter. More clarity.</span>
        </div>

        <div className="footer-links">
          <button onClick={() => setPrivacyOpen(true)}>Privacy Policy</button>

          <span>
            © {new Date().getFullYear()} DeskSweep. All rights reserved.
          </span>
        </div>
      </footer>
    </div>
  );
}
