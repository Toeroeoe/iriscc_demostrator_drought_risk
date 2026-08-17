# =============================================================================
# drought_hydrograph.R
# -----------------------------------------------------------------------------
# drought_hydrograph_plot(): builds the three-part drought graphic from a
# monthly discharge series supplied as an xts object.
#
#   MAIN    : decadal monthly hydrograph with two monthly Q thresholds
#   INSET L : decadal (total) drought-event count, paired by threshold
#   INSET R : monthly drought-event count (Jan..Dec), paired by threshold
#
# Monthly Q thresholds (10-yr & 50-yr return-period low flow) are computed
# INSIDE the function as per-calendar-month quantiles of the full input record.
# The plotted decade is chosen via the `decade` argument.
#
# Colours:  blue        -> monthly hydrograph
#           orange      -> 10-yr return period low flow (0.10 quantile)
#           dark orange -> 50-yr return period low flow (0.02 quantile)
#           black       -> axes and generic graphic elements
#
# Usage:
#   source("generate_synthetic_discharge.R")
#   source("drought_hydrograph.R")
#   q_xts <- generate_synthetic_discharge()
#   station <- list(name = "Musterstadt", id = "STN-0421",
#                   river = "Beispielfluss", catchment_area = "1234 km2")
#   p <- drought_hydrograph_plot(q_xts, decade = 1960:1969,
#                                persistence = 1, station = station)
#   ggsave("drought_hydrograph.png", p, width = 11, height = 9, dpi = 150, bg = "white")
# =============================================================================

# ---- packages ---------------------------------------------------------------
need <- c("ggplot2", "patchwork", "scales", "xts", "zoo")
for (p in need) if (!requireNamespace(p, quietly = TRUE))
  install.packages(p, repos = "https://cloud.r-project.org")
library(ggplot2)
library(patchwork)
library(xts)

# ---- global style -----------------------------------------------------------
FONT       <- "Helvetica"   # font family for the whole graphic

# Per-element font sizes
FS_AXTEXT  <- 14            # axis tick labels
FS_AXTITLE <- 16           # axis titles
FS_LEGEND  <- 14           # legend text
FS_TITLE   <- 18           # plot titles

col_q     <- "#1f4fd8"  # blue  - monthly hydrograph
col_10yr  <- "#f08c00"  # orange      - 10-yr return period
col_50yr  <- "#b23a00"  # dark orange - 50-yr return period
col_axis  <- "black"

FILL_ALPHA <- 0.60         # 60% opacity for all fills
LWD_MAIN   <- 1.4          # hydrograph line width
LWD_RP     <- 0.6          # RP line width

# Shared theme: Helvetica, per-element sizes, ticks INSIDE, no legend box,
# generous margins around axis labels, doubled title <-> plot gap.
theme_drought <- function() {
  theme_classic(base_size = FS_AXTEXT, base_family = FONT) +
    theme(
      text              = element_text(family = FONT, colour = col_axis),
      axis.line         = element_line(colour = col_axis),
      axis.ticks        = element_line(colour = col_axis),
      axis.ticks.length = unit(-3, "pt"),                 # ticks INSIDE
      axis.text         = element_text(colour = col_axis, size = FS_AXTEXT),
      axis.text.x       = element_text(margin = margin(t = 8)),
      axis.text.y       = element_text(margin = margin(r = 8)),
      axis.title        = element_text(colour = col_axis, size = FS_AXTITLE),
      axis.title.y      = element_text(colour = col_axis, size = FS_AXTITLE,
                                       margin = margin(r = 16)),
      plot.title        = element_text(colour = col_axis, size = FS_TITLE,
                                       margin = margin(b = 24)),
      plot.title.position = "plot",
      legend.background = element_blank(),
      legend.key        = element_blank(),
      legend.text       = element_text(size = FS_LEGEND)
    )
}

# integer y-breaks, capped at a maximum of 5 breaks
int_breaks_max5 <- function(l) {
  hi <- ceiling(l[2])
  b  <- seq(0, hi, by = 1)
  if (length(b) > 5) b <- unique(round(seq(0, hi, length.out = 5)))
  b
}

# smooth a series with a spline (non-negative), for the smooth curves/areas
smooth_series <- function(x, y, nout = 1000) {
  s <- spline(x, y, n = nout)
  data.frame(t = s$x, v = pmax(s$y, 0))
}

# =============================================================================
# drought_hydrograph_plot()
# -----------------------------------------------------------------------------
#' @param x           an xts object of monthly discharge. The discharge column
#'                    is taken as the first column (or the column named "Q").
#' @param decade      integer vector of the years to plot (default 1960:1969).
#' @param persistence minimum number of CONSECUTIVE months below a threshold for
#'                    those months to count as drought (default 1 = every month
#'                    below the threshold counts, i.e. no persistence filter).
#' @param station     named list describing the station, used to build the
#'                    overall title. Expected elements:
#'                      name          - station name
#'                      id            - station ID
#'                      river         - river name
#'                      catchment_area- drainage area (character or numeric,
#'                                      e.g. "1234 km2")
#' @return a patchwork object (the composed 3-part graphic). No file is written.
# =============================================================================
drought_hydrograph_plot <- function(x, decade = 1960:1969, persistence = 1,
                                     station = list(name = NA, id = NA,
                                                    river = NA,
                                                    catchment_area = NA)) {

  stopifnot(inherits(x, "xts"))
  stopifnot(is.numeric(persistence), length(persistence) == 1, persistence >= 1)
  months <- 1:12

  # Helper: given a logical vector of below-threshold flags (in time order),
  # keep TRUE only where it belongs to a run of >= `persistence` consecutive
  # TRUEs. persistence = 1 returns the input unchanged.
  apply_persistence <- function(below, k) {
    if (k <= 1) return(below)
    r <- rle(below)
    keep <- r$values & (r$lengths >= k)
    inverse.rle(list(lengths = r$lengths, values = keep))
  }

  # ---- xts -> tidy monthly data frame (year, month, Q) ----------------------
  qcol <- if ("Q" %in% colnames(x)) "Q" else colnames(x)[1]
  idx  <- zoo::index(x)
  flow <- data.frame(
    year  = as.integer(format(as.Date(idx), "%Y")),
    month = as.integer(format(as.Date(idx), "%m")),
    Q     = as.numeric(x[, qcol])
  )
  flow <- flow[order(flow$year, flow$month), ]

  # ---- monthly Q thresholds computed INSIDE the function --------------------
  #   10-yr return period -> 0.10 quantile ; 50-yr -> 0.02 quantile,
  #   per calendar month, from the FULL input record.
  p10 <- 1 / 10; p50 <- 1 / 50
  thr <- do.call(rbind, lapply(months, function(m) {
    qm <- flow$Q[flow$month == m]
    data.frame(month = m,
               thr_10yr = as.numeric(quantile(qm, p10)),
               thr_50yr = as.numeric(quantile(qm, p50)))
  }))

  # ---- flag drought events over the full record -----------------------------
  # Raw below-threshold, then keep only months inside runs of >= persistence
  # consecutive below-threshold months (time-ordered).
  flow <- merge(flow, thr, by = "month")
  flow <- flow[order(flow$year, flow$month), ]
  flow$drought_10yr <- apply_persistence(flow$Q < flow$thr_10yr, persistence)
  flow$drought_50yr <- apply_persistence(flow$Q < flow$thr_50yr, persistence)

  # ---- decade subset --------------------------------------------------------
  dec <- flow[flow$year %in% decade, ]
  if (nrow(dec) == 0)
    stop("No data in the requested decade: ", paste(range(decade), collapse = "-"))
  dec$t <- (dec$year - min(decade)) + (dec$month - 0.5) / 12

  dec_lo <- min(decade); dec_hi <- max(decade)
  dec_lbl <- sprintf("(%d-%d)", dec_lo, dec_hi)

  # percentage of the decade in hydrological drought (Q < 10-yr threshold)
  n_drought_months <- sum(dec$drought_10yr)
  drought_pct      <- 100 * n_drought_months / nrow(dec)
  drought_pct_lbl  <- sprintf("%.1f%%", drought_pct)

  # ---- smooth series for main plot ------------------------------------------
  thr_pts <- do.call(rbind, lapply(decade, function(y) {
    d <- thr
    d$t <- (y - min(decade)) + (d$month - 0.5) / 12
    d
  }))
  thr_pts <- thr_pts[order(thr_pts$t), ]
  s10 <- smooth_series(thr_pts$t, thr_pts$thr_10yr)
  s50 <- smooth_series(thr_pts$t, thr_pts$thr_50yr)
  sQ  <- smooth_series(dec$t,     dec$Q)

  year_breaks <- (decade - min(decade))
  year_labels <- decade

  # =============================================================================
  # MAIN PLOT
  # =============================================================================
  p_main <- ggplot() +
    geom_area(data = s10, aes(t, v, fill = "10-yr return period drought"),
              colour = col_10yr, linewidth = LWD_RP, alpha = FILL_ALPHA) +
    geom_area(data = s50, aes(t, v, fill = "50-yr return period drought"),
              colour = col_50yr, linewidth = LWD_RP, alpha = FILL_ALPHA) +
    geom_line(data = sQ, aes(t, v, colour = "Monthly hydrograph"),
              linewidth = LWD_MAIN) +
    scale_colour_manual(name = NULL, values = c("Monthly hydrograph" = col_q)) +
    scale_fill_manual(
      name = NULL,
      values = c("10-yr return period drought" = col_10yr,
                 "50-yr return period drought" = col_50yr),
      breaks = c("10-yr return period drought", "50-yr return period drought")
    ) +
    scale_x_continuous(breaks = year_breaks, labels = year_labels,
                       expand = expansion(mult = c(0.01, 0.01))) +
    scale_y_continuous(expand = expansion(mult = c(0, 0.05)),
                       breaks = scales::breaks_pretty(n = 5)) +
    labs(x = NULL, y = expression("streamflow (m"^3*"/s)"),
         title = sprintf("Decadal monthly hydrograph %s", dec_lbl)) +
    theme_drought() +
    theme(
      legend.position      = c(0.99, 0.99),
      legend.justification = c(1, 1),
      legend.spacing.y     = unit(1, "pt"),
      legend.margin        = margin(4, 6, 4, 6),
      legend.background    = element_rect(fill = "white", colour = NA),
      # enlarge ONLY the first year label to 28 pt (tick over its 3rd digit).
      axis.text.x = element_text(size  = c(28, rep(FS_AXTEXT, length(year_breaks) - 1)),
                                 hjust = c(0.625, rep(0.5, length(year_breaks) - 1)),
                                 margin = margin(t = 8))
    ) +
    guides(
      colour = guide_legend(order = 1,
                override.aes = list(fill = NA, linewidth = LWD_MAIN)),
      fill   = guide_legend(order = 2,
                override.aes = list(colour = NA, alpha = FILL_ALPHA))
    )

  # ---- annotation at (0.05, 0.85) in panel npc coordinates ------------------
  # xx% on top (28 pt, bold) then a three-line sentence (18 pt).
  ann_x <- 0.05; ann_y <- 0.88; dy <- 0.08
  ann_grob <- grid::grobTree(
    grid::textGrob(drought_pct_lbl,               x = ann_x, y = ann_y,
                   hjust = 0, gp = grid::gpar(fontsize = 28, fontfamily = FONT,
                                              fontface = "bold", col = col_axis)),
    grid::textGrob("of the decade",               x = ann_x, y = ann_y - dy,
                   hjust = 0, gp = grid::gpar(fontsize = 18, fontfamily = FONT,
                                              col = col_axis)),
    grid::textGrob("the river segment was",       x = ann_x, y = ann_y - 2 * dy,
                   hjust = 0, gp = grid::gpar(fontsize = 18, fontfamily = FONT,
                                              col = col_axis)),
    grid::textGrob("modelled under drought",      x = ann_x, y = ann_y - 3 * dy,
                   hjust = 0, gp = grid::gpar(fontsize = 18, fontfamily = FONT,
                                              col = col_axis))
  )
  p_main <- p_main +
    annotation_custom(ann_grob, xmin = -Inf, xmax = Inf, ymin = -Inf, ymax = Inf)

  # =============================================================================
  # Event counts (mutually exclusive bands): Q10-only vs Q50
  # =============================================================================
  band_levels <- c("Q10", "Q50")
  band_cols   <- c("Q10" = col_10yr, "Q50" = col_50yr)

  # ---- INSET R: monthly (Jan..Dec) ----
  mcount <- do.call(rbind, lapply(months, function(m) {
    sub <- dec[dec$month == m, ]
    data.frame(month = m,
               band  = band_levels,
               count = c(sum(sub$drought_10yr & !sub$drought_50yr),
                         sum(sub$drought_50yr)))
  }))
  month_initial <- c("J","F","M","A","M","J","J","A","S","O","N","D")
  mcount$month <- factor(mcount$month, levels = months, labels = month_initial)
  mcount$band  <- factor(mcount$band, levels = band_levels)

  p_month <- ggplot(mcount, aes(month, count, fill = band, colour = band)) +
    geom_col(width = 0.55, position = position_dodge(width = 0.55),
             alpha = FILL_ALPHA, linewidth = 0.8) +
    scale_fill_manual(values = band_cols, guide = "none") +
    scale_colour_manual(values = band_cols, guide = "none") +
    scale_y_continuous(expand = expansion(mult = c(0, 0.08)),
                       breaks = scales::breaks_pretty()) +   # pretty breaks
    labs(x = NULL, y = "event count",
         title = sprintf("Drought events across the months\n%s", dec_lbl)) +
    theme_drought() +
    theme(legend.position = "none")

  # ---- INSET L: decadal totals ----
  tot <- data.frame(
    band  = factor(band_levels, levels = band_levels),
    count = c(sum(dec$drought_10yr & !dec$drought_50yr),
              sum(dec$drought_50yr))
  )

  p_total <- ggplot(tot, aes(x = 1, y = count, fill = band, colour = band)) +
    geom_col(width = 0.5, position = position_dodge(width = 0.5),
             alpha = FILL_ALPHA, linewidth = 0.8) +
    geom_text(aes(label = count), position = position_dodge(width = 0.5),
              vjust = -0.8, size = 18 / .pt, fontface = "bold",
              family = FONT, colour = col_axis) +
    scale_fill_manual(values = band_cols, guide = "none") +
    scale_colour_manual(values = band_cols, guide = "none") +
    scale_x_continuous(breaks = NULL) +
    scale_y_continuous(expand = expansion(mult = c(0, 0.18)),
                       breaks = scales::breaks_pretty()) +
    labs(x = NULL, y = "event count",
         title = sprintf("Total drought events\n%s", dec_lbl)) +
    theme_drought() +
    theme(legend.position = "none")

  # ---- overall (super) title, two lines -------------------------------------
  #   line 1: BOLD "Monthly hydrological drought" + 16pt "(<decade>s, persistence = <x> months)"
  #   line 2: 22pt "<River> at <station> " + 16pt "(<ID>, A = <area>)"
  decade_tag <- sprintf("%ds", (dec_lo %/% 10) * 10)   # e.g. 1960 -> "1960s"
  l1_main  <- "Monthly hydrological drought "
  l1_paren <- sprintf("(%s, persistence = %d months)", decade_tag, as.integer(persistence))
  l2_main  <- sprintf("%s at %s ", station$river, station$name)
  l2_paren <- sprintf("(%s, A = %s)", station$id, station$catchment_area)

  FS_TITLE_MAIN  <- 22
  FS_TITLE_PAREN <- 16

  # Title as its own panel (theme_void). Each line = a big/bold main segment
  # followed by a 16 pt parenthetical placed right after it via grobWidth.
  # Lines are positioned in ABSOLUTE units measured DOWN from the panel TOP so
  # there is no dead space above the title; the inter-line gap is explicit.
  gp_main1  <- grid::gpar(fontsize = FS_TITLE_MAIN,  fontfamily = FONT,
                          fontface = "bold", col = col_axis)
  gp_main2  <- grid::gpar(fontsize = FS_TITLE_MAIN,  fontfamily = FONT, col = col_axis)
  gp_paren  <- grid::gpar(fontsize = FS_TITLE_PAREN, fontfamily = FONT, col = col_axis)

  line1_gap <- grid::unit(14, "pt")            # extra gap between the two lines
  y_line1 <- grid::unit(1, "npc") - grid::unit(2, "pt")               # line 1 top
  y_line2 <- y_line1 - grid::unit(FS_TITLE_MAIN, "pt") - line1_gap    # line 2 top

  title_grob <- grid::grobTree(
    # line 1 (vjust = 1 => text hangs from its top edge, flush to panel top)
    grid::textGrob(l1_main, x = grid::unit(0, "npc"), y = y_line1,
                   hjust = 0, vjust = 1, gp = gp_main1),
    grid::textGrob(l1_paren,
                   x = grid::grobWidth(grid::textGrob(l1_main, gp = gp_main1)),
                   y = y_line1, hjust = 0, vjust = 1, gp = gp_paren),
    # line 2
    grid::textGrob(l2_main, x = grid::unit(0, "npc"), y = y_line2,
                   hjust = 0, vjust = 1, gp = gp_main2),
    grid::textGrob(l2_paren,
                   x = grid::grobWidth(grid::textGrob(l2_main, gp = gp_main2)),
                   y = y_line2, hjust = 0, vjust = 1, gp = gp_paren)
  )
  p_title <- ggplot() +
    annotation_custom(title_grob, xmin = 0, xmax = 1, ymin = 0, ymax = 1) +
    scale_x_continuous(limits = c(0, 1), expand = c(0, 0)) +
    scale_y_continuous(limits = c(0, 1), expand = c(0, 0)) +
    theme_void() +
    theme(plot.margin = margin(0, 0, 0, 0))

  # =============================================================================
  # Compose: title / gap1 / insets / gap2 / main.
  #   gap1 (title <-> insets) == gap2 (insets <-> main)  (equal spacing)
  # =============================================================================
  sp  <- plot_spacer()
  top <- p_total + sp + p_month + plot_layout(widths = c(0.5, 0.43, 1.43))

  gap <- 1.0
  final <- p_title / sp / top / sp / p_main +
    plot_layout(heights = c(0.55, gap, 0.75, gap, 1.9)) +   # title / gap / insets / gap / main
    # trim the outer figure margin so there is no space above the title
    plot_annotation(theme = theme(plot.margin = margin(t = 0, r = 6, b = 6, l = 6)))

  final
}

# Build + save one PNG for a (dataset, station) pair, using the file-name
# convention: drought_hydrograph_<station id>_<decade>_<persistence>.png
save_drought_hydrograph <- function(x, station, decade = 1960:1969,
                                    persistence = 1) {
  p <- drought_hydrograph_plot(x, decade = decade,
                               persistence = persistence, station = station)
  decade_tag <- sprintf("%ds", (min(decade) %/% 10) * 10)   # e.g. "1960s"
  outfile <- sprintf("drought_hydrograph_%s_%s_%d.png",
                     station$id, decade_tag, as.integer(persistence))
  # Taller canvas gives each row more absolute room so multi-line text
  # (super-title, annotation) is not crushed. Dead space above the title is
  # controlled at the layout level (title row height + t=0 outer margin).
  ggsave(outfile, p, width = 11, height = 11, dpi = 150, bg = "white")
  cat("Saved", outfile, "\n")
  invisible(outfile)
}

# When sourced non-interactively with the data helper present, build + save
# BOTH synthetic datasets (normal + big-1960s-droughts).
if (identical(environment(), globalenv()) &&
    exists("generate_synthetic_discharge", mode = "function")) {
  # objects created by generate_synthetic_discharge.R: q_normal, q_severe,
  # meta_normal, meta_severe.
  save_drought_hydrograph(q_normal, meta_normal, decade = 1960:1969, persistence = 3)
  save_drought_hydrograph(q_severe, meta_severe, decade = 1960:1969, persistence = 3)
}
