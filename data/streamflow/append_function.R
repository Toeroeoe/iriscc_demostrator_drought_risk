#' Create drought hydrograph from raw date strings and values
#'
#' This is a wrapper function designed for Python/rpy2 integration.
#' It accepts dates as character strings and values as numeric vector,
#' creates an xts object internally, and generates the drought hydrograph.
#'
#' @param dates Character vector of dates in "YYYY-MM-DD" format
#' @param values Numeric vector of discharge values
#' @param gauge_id Gauge ID
#' @param station_name Station name
#' @param station_river River name
#' @param station_country Country
#' @param station_area Catchment area
#' @param decade_years Integer vector of years to plot
#' @param persistence Minimum consecutive months below threshold
#' @param output_dir Output directory
#' @param filename Optional custom filename
#' @return Path to saved PNG
#' @export
drought_hydrograph_from_dates <- function(dates, values, gauge_id,
                                           station_name, station_river, station_country,
                                           station_area, decade_years = 1960:1969,
                                           persistence = 1,
                                           output_dir = tempdir(), filename = NULL) {
  
  # Create xts object from dates and values
  dates <- as.Date(dates)
  x <- xts(values, order.by = dates)
  
  # Create station metadata list
  station <- list(
    name = station_name,
    id = gauge_id,
    river = station_river,
    country = station_country,
    catchment_area = station_area
  )
  
  # Generate plot
  p <- drought_hydrograph_plot(
    x = x,
    decade = decade_years,
    persistence = as.integer(persistence),
    station = station
  )
  
  # Determine output filename
  if (is.null(filename)) {
    decade_tag <- sprintf("%ds", (min(decade_years) %/% 10) * 10)
    filename <- sprintf("drought_hydrograph_%s_%s_%d.png",
                        gauge_id, decade_tag, as.integer(persistence))
  }
  
  # Save to file
  outfile <- file.path(output_dir, filename)
  ggsave(outfile, p, width = 11, height = 11, dpi = 150, bg = "transparent")
  
  cat("Saved drought hydrograph to:", outfile, "\n")
  invisible(outfile)
}
