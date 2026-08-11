import pandas as pd
import numpy as np
import matplotlib.pyplot as plt


def temp_transform(temp, fish_csv):
    df = pd.read_csv(fish_csv)
    x= df["Temperature.C"].to_numpy()
    y= df["Specific.Growth.Rate.g.g.d"].to_numpy()

    poly_model = np.polynomial.Polynomial.fit(x, y, deg=6)
    if temp > 25:
        return -0.015*1000
    else:
        return poly_model(temp)*1000

def vis(path): # NOT USED IN APP
    '''Visualise curve for fishtable'''
    df = pd.read_csv(path)
    x= df["Temperature.C"].to_numpy()
    y= df["Specific.Growth.Rate.g.g.d"].to_numpy()
    
    poly_model = np.polynomial.Polynomial.fit(x, y, deg=6)

    x_line = np.linspace(x.min(), x.max(), 100)
    y_line = poly_model(x_line)

    plt.scatter(x, y, color="red", label="Data Points")
    plt.plot(x_line, y_line, color="blue", label=f"Best Fit (Degree {poly_model.degree})")
    plt.xlabel("Temp")
    plt.ylabel("Growth Rate")
    plt.grid(True)
    plt.show()
