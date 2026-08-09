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
    [JsonPropertyName("file_path")]
    public string FilePath { get; set; } = "";

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
        set { if (SetProperty(ref _downloadedBytes, value)) OnPropertyChanged(nameof(Progress)); }
    }

    [JsonPropertyName("total_bytes")]
    public long TotalBytes
    {
        get => _totalBytes;
        set { if (SetProperty(ref _totalBytes, value)) OnPropertyChanged(nameof(Progress)); }
    }

    [JsonPropertyName("speed_bps")]
    public double SpeedBps
    {
        get => _speedBps;
        set => SetProperty(ref _speedBps, value);
    }

    [JsonPropertyName("error")]
    public string Error
    {
        get => _error;
        set => SetProperty(ref _error, value);
    }

    public double Progress
    {
        get
        {
            if (TotalBytes == 0) return 0;
            return (double)DownloadedBytes / TotalBytes * 100.0;
        }
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
