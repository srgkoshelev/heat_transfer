from math import log, log10
from . import logger
from . import ureg, Q_
from . import Air
from .rp_wrapper import *


# Basic thermodynamic functions
def spec_heat(Fluid_data):
    """
    Calculate latent heat/specific heat input for given conditions.
    For subcritical flow returns latent heat of evaporation,
    for supercritical: specific heat input
    """
    x,M,D = rp_init(Fluid_data)
    _,T,P = unpack_fluid(Fluid_data)
    crit_props = info()
    T_crit = crit_props['tcrit']
    D_crit = crit_props['Dcrit']
    P_crit = flsh('TD', T_crit, D_crit, x)['p']
    if T < T_crit and P < P_crit: #Two phase region only possible below critical point
        props = flsh('TP', T, P, x)
        quality = props['q']
        if quality < 1: #For 2 phase region (including subcooled liquid) using latent heat of evaporation
            props = satp(P, x)
            Dliq = props['Dliq']
            Dvap = props['Dvap']
            h_liq = flsh('TD', T, Dliq, x)['h']
            h_vap = flsh('TD', T, Dvap, x)['h']
            L = (h_vap - h_liq)/M
        else:
            L = therm3(T,D,x)['spht']/M #Specific heat input
    else:
        L = therm3(T,D,x)['spht']/M #Specific heat input
    return L

def to_scfma (M_dot, Fluid_data):
        """
        Convert mass flow rate into SCFM of air.
        Assumption: Flow through a relief device with invariant Area/discharge coefficient (KA).
        """
        (x_fluid, M_fluid, D_fluid) = rp_init(Fluid_data)
        T_fluid = Fluid_data['T']
        Z_fluid = therm2(T_fluid, D_fluid, x_fluid)['Z'] #Compressibility factor
        (x_air, M_air, D_air) = rp_init(Air)
        T_air = Air['T']
        Z_air = therm2(T_air, D_air, x_air)['Z'] #Compressibility factor
        Q_air =  M_dot*C_gas_const(Air)/(D_air*M_air*C_gas_const(Fluid_data))*(T_fluid*Z_fluid*M_air/(M_fluid*T_air*Z_air))**0.5
        Q_air.ito(ureg.ft**3/ureg.min)
        return Q_air

def from_scfma (Q_air, Fluid_data):
        """
        Convert SCFM of air into mass flow of specified fluid.
        """
        (x_fluid, M_fluid, D_fluid) = rp_init(Fluid_data)
        T_fluid = Fluid_data['T']
        Z_fluid = therm2(T_fluid, D_fluid, x_fluid)['Z'] #Compressibility factor
        (x_air, M_air, D_air) = rp_init(Air)
        T_air = Air['T']
        Z_air = therm2(T_air, D_air, x_air)['Z'] #Compressibility factor
        M_dot =  Q_air/(C_gas_const(Air))*(D_air*M_air*C_gas_const(Fluid_data))/(T_fluid*Z_fluid*M_air/(M_fluid*T_air*Z_air))**0.5
        M_dot.ito(ureg.kg/ureg.s)
        return M_dot

def gamma (Fluid_data = {'fluid':'air', 'P':Q_(101325,ureg.Pa), 'T':Q_(15,ureg.degC)}):
    """
    Calculate gamma (k) coefficient for the fluid
    gamma = k = Cp/Cv
    """
    (fluid, T_fluid, P_fluid) = unpack_fluid(Fluid_data)
    (x, M, D_fluid) = rp_init(Fluid_data)
    fluid_prop = flsh ("TP", T_fluid, P_fluid, x)
    Cp = fluid_prop['cp']
    Cv = fluid_prop['cv']
    return Cp/Cv
k = gamma # A useful shortcut

def max_theta(Fluid_data, step = 0.01):
        """Calculate tepmerature at which sqrt(v)/SHI is max for safety calculations (CGA S-1.3 2008)
        SHI - specific heat input v*(dh/dv)|p
        step - temperature step
        """
        x, _, _ = rp_init(Fluid_data)
        T_start = satp(Q_(101325, ureg.Pa),x)['t']  #Starting temperature - liquid temperature for atmospheric pressure. Vacuum should be handled separately.
        T_end = 300*ureg.K
        theta = ureg('0 mol**1.5/(J*l**0.5)')
        T = T_start
        P = Fluid_data['P']
        while T <= T_end:
            D_vap = flsh('TP', T, P, x)['Dvap']
            theta_new = (D_vap**0.5)/therm3(T, D_vap, x)['spht'] 
            if theta_new > theta:
                theta = theta_new
            else:
                break #Function has only one maximum
            T += step*ureg.K
        return T

def C_gas_const (Fluid_data):
        """
        Constant for gal or vapor which is the function of the ratio of specific heats k = Cp/Cv. ASME VIII.1-2015 pp. 423-424.
        """
        k_ = k(Fluid_data)
        C = 520*(k_*(2/(k_+1))**((k_+1)/(k_-1)))**0.5*ureg('lb/(hr*lbf)*(degR)^0.5')
        return C

#' Radiation heat leak through the baffles.
def rad_hl (eps_cold = 0.55, eps_hot = 0.55, T_hot = 300*ureg.K, T_cold = 77*ureg.K, F1_2 = 1, eps_baffle = 0.02, N_baffles = 5):
        """
        Calculate radiative heat load including reduction due to baffles
        Based on Kaganer "Thermal insulation in cryogenic engineering", p. 42.
        F1_2 = F_cold/F_hot
        """
        
        Eps_mut = 1/(1/eps_cold + F1_2*(1/eps_hot-1)) #Mutual emissivity
        q0 = Eps_mut*sigma*(T_hot**4 - T_cold**4)*F1_2
        Eps_baffle_mut = eps_baffle/(2-eps_baffle)
        eta = (1+N_baffles*Eps_mut/Eps_baffle_mut)**(-1)
        q_baffle = eta*q0
        return {'q0':q0.to(ureg.W/ureg.m**2), 'q_baffle':q_baffle.to(ureg.W/ureg.m**2), 'eta':eta}

#' Functions for basic dimensionless quantities (Re number is a part of piping module).
def Pr(Fluid_data):
        """
        Calculate Prandtl number for given fluid
        Properties of fluid are obtained from Refprop package
        """
        (fluid, T_fluid, P_fluid) = unpack_fluid(Fluid_data)
        (x, M, D_fluid) = rp_init(Fluid_data)
        fluid_trans_prop = trnprp(T_fluid, D_fluid, x)
        mu = fluid_trans_prop['eta'] #dynamic viscosity
        k = fluid_trans_prop['tcx'] #thermal conductivity
        nu = mu/(D_fluid*M) #kinematic viscosity
        Cp = flsh("TP", T_fluid, P_fluid, x)['cp']/M
        Prandtl = Cp*mu/k
        return Prandtl.to_base_units()

def Gr(Fluid_data, T_surf, L_surf):
        """
        Calculate Grashof number for given fluid and surface
        Properties of fluid are obtained from Refprop package
        L_surf - characteristic length
        """
        (fluid, T_fluid, P_fluid) = unpack_fluid(Fluid_data)
        (x, M, D_fluid) = rp_init(Fluid_data)
        fluid_trans_prop = trnprp(T_fluid, D_fluid, x)
        mu_fluid = fluid_trans_prop['eta'] #dynamic viscosity
        nu_fluid = mu_fluid/(D_fluid*M) #kinematic viscosity
        beta_exp = 1/(T_fluid.to('K')) #volumetric thermal expansion coefficient
        Grashof = ureg.g_0 * L_surf**3 * beta_exp * (T_fluid-T_surf) / nu_fluid**2 #Grashof number
        return Grashof.to_base_units()

def Ra (Fluid_data, T_surf, L_surf):
        """
        Calculate Rayleigh number for given fluid and surface
        Properties of fluid are obtained from Refprop package
        L_surf - characteristic length
        """
        return  Gr(Fluid_data, T_surf, L_surf)*Pr(Fluid_data) 

def Nu_cyl_hor(Fluid_data, T_cyl, D_cyl):
        """
        Calculate Nusselt number for given Fluid around horizontal cylinder.
        Only natural convection currently supported.
        Properties of fluid are obtained from Refprop package
        """
        Prandtl = Pr(Fluid_data)
        Rayleigh = Ra(Fluid_data, T_cyl, D_cyl)
        C_l = 0.671/(1+(0.492/Prandtl)**(9/16))**(4/9) #Handbook of heat transfer, Rohsenow, Hartnet, Cho (4.13)
        Nu_T = 0.772*C_l*Rayleigh**(1/4) #Handbook of heat transfer, Rohsenow, Hartnet, Cho (4.45)
        f = 1-0.13/Nu_T**0.16
        Nu_l = 2*f/log(1+2*f*Nu_T)
        C_t = 0.0002*log(Prandtl)**3 - 0.0027*log(Prandtl)**2 + 0.0061*log(Prandtl) + 0.1054
        Nu_t = 0.103*Rayleigh**(1/3)
        Nusselt = (Nu_l**10 + Nu_t**10)**(1/10) #Nu number, Handbook of heat transfer, Rohsenow, Hartnet, Cho
        return Nusselt.to_base_units()

def Nu_cyl_vert(Fluid_data, T_cyl, D_cyl, L_cyl):
        """
        Calculate Nusselt number for given Fluid around horizontal cylinder.
        Only natural convection currently supported.
        Properties of fluid are obtained from Refprop package
        """
        Prandtl = Pr(Fluid_data)
        Rayleigh = Ra(Fluid_data, T_cyl, D_cyl)
        C_l = 0.671/(1+(0.492/Prandtl)**(9/16))**(4/9) #Handbook of heat transfer, Rohsenow, Hartnet, Cho (4.13)
        C_t_vert = (0.13*Prandtl**0.22)/(1+0.61*Prandtl**0.81)**0.42 #Handbook of heat transfer, Rohsenow, Hartnet, Cho (4.24)
        Nu_T_plate = C_l * Rayleigh**0.25
        Nu_l_plate = 2 / log(1+2/Nu_T_plate) #Handbook of heat transfer, Rohsenow, Hartnet, Cho (4.33)
        zeta = 1.8 * L_cyl / (D_cyl*Nu_T_plate)  #Handbook of heat transfer, Rohsenow, Hartnet, Cho (4.44)
        Nu_l = zeta / (log(1+zeta)*Nu_l_plate)
        Nu_t = C_t_vert*Rayleigh**(1/3)/(1+1.4e9*Prandtl/Rayleigh)
        Nusselt = (Nu_l**6 + Nu_t**6)**(1/6)
        return Nusselt.to_base_units()

def  heat_trans_coef(Fluid_data, Nu, L_surf):
        """
        Calculate heat transfer coefficient
        L_surf - characteristic length:
            Horizontal cylinder: L_surf = D_cyl
            Vertical cylinder: L_surf = L_cyl
        """
        x,M,D = rp_init(Fluid_data)
        k_fluid = trnprp(T_fluid, D_fluid, x)['tcx']
        return k_fluid*Nu/L_surf









