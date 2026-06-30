$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$DataDir = Join-Path $AppDir "data"
$GeoJsonPath = Join-Path $DataDir "gd_sites_swedes.geojson"
$OutCsv = Join-Path $DataDir "gd_site_online_forecasts.csv"
$ServiceUrl = "https://livefeeds3.arcgis.com/arcgis/rest/services/GEOGLOWS/GlobalWaterModel_Medium/MapServer"

function Invoke-ArcJson {
    param([Parameter(Mandatory=$true)][string]$Url)
    try {
        return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 25
    } catch {
        return $null
    }
}

function Invoke-ArcQuery {
    param([Parameter(Mandatory=$true)][hashtable]$Params)
    $args = @("-s", "--max-time", "25", "-G", "$ServiceUrl/0/query")
    foreach ($key in $Params.Keys) {
        $args += "--data-urlencode"
        $args += "$key=$($Params[$key])"
    }
    $raw = & curl.exe @args
    if (-not $raw) { return $null }
    return $raw | ConvertFrom-Json
}

function Encode-Query {
    param([Parameter(Mandatory=$true)][hashtable]$Params)
    $pairs = foreach ($key in $Params.Keys) {
        "$([uri]::EscapeDataString([string]$key))=$([uri]::EscapeDataString([string]$Params[$key]))"
    }
    return ($pairs -join "&")
}

function Build-NearUrl {
    param(
        [double]$Lon,
        [double]$Lat,
        [int]$Distance
    )
    $geom = ([string]::Format([Globalization.CultureInfo]::InvariantCulture, "{0},{1}", $Lon, $Lat))
    return "$ServiceUrl/0/query?f=json&where=1%3D1&geometry=$geom&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&distance=$Distance&units=esriSRUnit_Meter&outFields=comid,streamorder,rivercountry,timevalue,meanflow,returnperiod,upstreamarea&returnGeometry=false&orderByFields=streamorder%20DESC%2Cupstreamarea%20DESC&resultRecordCount=1"
}

if (-not (Test-Path $GeoJsonPath)) {
    throw "GD Sites GeoJSON not found: $GeoJsonPath"
}

$geo = Get-Content -LiteralPath $GeoJsonPath -Raw | ConvertFrom-Json
$rows = New-Object System.Collections.Generic.List[object]
$generatedAt = (Get-Date).ToString("o")

foreach ($feature in $geo.features) {
    $props = $feature.properties
    $geom = $feature.geometry
    if (-not $geom -or -not $geom.coordinates) { continue }
    $lon = [double]$geom.coordinates[0]
    $lat = [double]$geom.coordinates[1]
    $stationCode = [string]$props.'Station Co'
    if ([string]::IsNullOrWhiteSpace($stationCode)) { continue }

    $nearParams = @{
        f = "json"
        where = "1=1"
        geometry = ([string]::Format([Globalization.CultureInfo]::InvariantCulture, "{0},{1}", $lon, $lat))
        geometryType = "esriGeometryPoint"
        inSR = "4326"
        spatialRel = "esriSpatialRelIntersects"
        distance = "150000"
        units = "esriSRUnit_Meter"
        outFields = "comid,streamorder,rivercountry,timevalue,meanflow,returnperiod,upstreamarea"
        returnGeometry = "false"
        orderByFields = "streamorder DESC,upstreamarea DESC"
        resultRecordCount = "1"
    }
    $near = Invoke-ArcQuery $nearParams
    if (-not $near -or -not $near.features -or $near.features.Count -eq 0) {
        $rows.Add([pscustomobject]@{
            generated_at = $generatedAt
            station_code = $stationCode
            station_name = [string]$props.'Station Na'
            district = [string]$props.District
            river = [string]$props.River
            tributary = [string]$props.Tributary
            latitude = $lat
            longitude = $lon
            comid = $null
            streamorder = $null
            forecast_time = $null
            lead_day = 0
            meanflow_cms = $null
            returnperiod = $null
            linkage_status = "Not linked"
        })
        continue
    }

    $attrs = $near.features[0].attributes
    $comid = $attrs.comid
    $seriesParams = @{
        f = "json"
        where = "comid=$comid"
        outFields = "comid,streamorder,rivercountry,timevalue,meanflow,returnperiod,upstreamarea"
        returnGeometry = "false"
        orderByFields = "timevalue ASC"
        resultRecordCount = "80"
    }
    $series = Invoke-ArcQuery $seriesParams
    $lead = 0
    if ($series -and $series.features) {
        foreach ($item in $series.features) {
            $a = $item.attributes
            $forecastTime = $null
            if ($a.timevalue) {
                $forecastTime = ([DateTimeOffset]::FromUnixTimeMilliseconds([int64]$a.timevalue)).ToLocalTime().ToString("o")
            }
            $rows.Add([pscustomobject]@{
                generated_at = $generatedAt
                station_code = $stationCode
                station_name = [string]$props.'Station Na'
                district = [string]$props.District
                river = [string]$props.River
                tributary = [string]$props.Tributary
                latitude = $lat
                longitude = $lon
                comid = $a.comid
                streamorder = $a.streamorder
                forecast_time = $forecastTime
                lead_day = $lead
                meanflow_cms = $a.meanflow
                returnperiod = $a.returnperiod
                linkage_status = "Linked drainage reach"
            })
            $lead += 1
        }
    }
}

$rows | Export-Csv -LiteralPath $OutCsv -NoTypeInformation -Encoding UTF8
Write-Output "Saved $($rows.Count) GD site online forecast rows to $OutCsv"
