using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Text.Json.Serialization;

namespace DownloadManagerUI.Models;

public class DownloadTask : INotifyPropertyChanged
{
    private string _status = "PENDING";
    private long _downloadedBytes;
    private long _totalBytes;
    private double _speedBps;
    private string _error = "";

    [JsonPropertyName("id")]
    public string Id { get; set; } = "";
    [JsonPropertyName("source")]
    public string Source { get; set; } = "";
    [JsonPropertyName("priority")]
    public string Priority { get; set; } = "NORMAL";
    private string _filePath = "";
    
    [JsonPropertyName("file_path")]
    public string FilePath
    {
        get => _filePath;
        set
        {
            if (SetProperty(ref _filePath, value))
            {
                OnPropertyChanged(nameof(Filename));
            }
        }
    }
    
    public string Filename
    {
        get
        {
            var name = System.IO.Path.GetFileName(_filePath);
            return string.IsNullOrEmpty(name) ? Source : name;
        }
    }

    [JsonPropertyName("status")]
    public string Status
    {
        get => _status;
        set => SetProperty(ref _status, value);
    }

    [JsonPropertyName("downloaded_bytes")]
    public long DownloadedBytes
    {
        get => _downloadedBytes;
        set { if (SetProperty(ref _downloadedBytes, value)) { OnPropertyChanged(nameof(Progress)); OnPropertyChanged(nameof(ProgressText)); OnPropertyChanged(nameof(SizeText)); OnPropertyChanged(nameof(ETAText)); } }
    }

    [JsonPropertyName("total_bytes")]
    public long TotalBytes
    {
        get => _totalBytes;
        set { if (SetProperty(ref _totalBytes, value)) { OnPropertyChanged(nameof(Progress)); OnPropertyChanged(nameof(ProgressText)); OnPropertyChanged(nameof(SizeText)); OnPropertyChanged(nameof(ETAText)); } }
    }

    [JsonPropertyName("speed_bps")]
    public double SpeedBps
    {
        get => _speedBps;
        set { if (SetProperty(ref _speedBps, value)) { OnPropertyChanged(nameof(SpeedText)); OnPropertyChanged(nameof(ETAText)); } }
    }

    [JsonPropertyName("error")]
    public string Error
    {
        get => _error;
        set { if (SetProperty(ref _error, value)) OnPropertyChanged(nameof(ErrorVisibility)); }
    }

    public Microsoft.UI.Xaml.Visibility ErrorVisibility => string.IsNullOrEmpty(Error) ? Microsoft.UI.Xaml.Visibility.Collapsed : Microsoft.UI.Xaml.Visibility.Visible;

    public double Progress
    {
        get
        {
            if (TotalBytes == 0) return 0;
            return (double)DownloadedBytes / TotalBytes * 100.0;
        }
    }

    public string ProgressText => $"{Progress:F1}%";

    public string SizeText
    {
        get
        {
            if (TotalBytes == 0) return FormatBytes(DownloadedBytes);
            return $"{FormatBytes(DownloadedBytes)} / {FormatBytes(TotalBytes)}";
        }
    }

    public string SpeedText => SpeedBps > 0 ? $"{FormatBytes((long)SpeedBps)}/s" : "";

    public string ETAText
    {
        get
        {
            if (SpeedBps <= 0 || TotalBytes == 0 || DownloadedBytes >= TotalBytes || Status != "DOWNLOADING") return "";
            var remainingBytes = TotalBytes - DownloadedBytes;
            var seconds = (double)remainingBytes / SpeedBps;
            if (seconds > 3600) return $"{(int)(seconds / 3600)}h {((int)seconds % 3600) / 60}m";
            if (seconds > 60) return $"{(int)(seconds / 60)}m {(int)(seconds % 60)}s";
            return $"{(int)seconds}s remaining";
        }
    }

    private static string FormatBytes(long bytes)
    {
        string[] suffixes = { "B", "KB", "MB", "GB", "TB" };
        int counter = 0;
        decimal number = bytes;
        while (Math.Round(number / 1024) >= 1)
        {
            number = number / 1024;
            counter++;
        }
        return $"{number:n1} {suffixes[counter]}";
    }

    public event PropertyChangedEventHandler? PropertyChanged;
    protected void OnPropertyChanged([CallerMemberName] string? propertyName = null)
        => PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));

    protected bool SetProperty<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }
}


public class AppConfig
{
    [JsonPropertyName("download_dir")]
    public string DownloadDir { get; set; } = "";

    [JsonPropertyName("max_concurrent_downloads")]
    public int MaxConcurrentDownloads { get; set; } = 3;

    [JsonPropertyName("global_bandwidth_limit")]
    public int GlobalBandwidthLimit { get; set; } = 0;
}

public class VideoFormat
{
    [JsonPropertyName("format_id")]
    public string FormatId { get; set; } = "";

    [JsonPropertyName("ext")]
    public string Ext { get; set; } = "";

    [JsonPropertyName("resolution")]
    public string Resolution { get; set; } = "";

    [JsonPropertyName("filesize")]
    public long Filesize { get; set; } = 0;

    [JsonPropertyName("vcodec")]
    public string VCodec { get; set; } = "";

    [JsonPropertyName("acodec")]
    public string ACodec { get; set; } = "";

    [JsonPropertyName("format_note")]
    public string FormatNote { get; set; } = "";

    public string DisplayText
    {
        get
        {
            var size = Filesize > 0 ? $" ({Filesize / 1024 / 1024} MB)" : "";
            var codecInfo = "";
            if (VCodec != "none" && ACodec != "none") codecInfo = "[Video + Audio]";
            else if (VCodec != "none") codecInfo = "[Video Only]";
            else if (ACodec != "none") codecInfo = "[Audio Only]";

            return $"{Resolution} - {Ext} {codecInfo} - {FormatNote}{size}";
        }
    }
}
