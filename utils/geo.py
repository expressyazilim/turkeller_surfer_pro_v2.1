import plotly.graph_objects as go
import matplotlib.pyplot as plt
import numpy as np

def zscore_to_heatmap(Z_z):
    plt.figure(figsize=(6,4))
    plt.imshow(Z_z, origin="lower", cmap="RdBu")
    plt.colorbar(label="Z")
    plt.title("Z-Skor Heatmap")
    plt.tight_layout()
    return plt

def zscore_to_surface(Z_z):
    H, W = Z_z.shape
    X, Y = np.meshgrid(np.arange(W), np.arange(H))
    fig = go.Figure(data=[
        go.Surface(z=Z_z, x=X, y=Y, colorscale="RdBu", showscale=True)
    ])
    fig.update_layout(title="3D Z-Surface", scene=dict(
        xaxis_title="X",
        yaxis_title="Y",
        zaxis_title="Z"))
    return fig

def plot_map(lat, lon):
    return [{"lat": lat, "lon": lon}]